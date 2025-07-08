from truedata_ws.websocket.TD import TD
from datetime import datetime, timezone
import threading
import queue
import streamlit as st
from database import DatabaseManager
from copy import deepcopy
import time

class TrueDataFeed:
    def __init__(self, username, password, symbols):
        self.username = username
        self.password = password
        self.symbols = symbols
        self.data_queue = queue.Queue()
        self.message_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.td_app = None
        self.req_ids = []
        self.live_data_objs = {}

    def start_feed(self):
        if not self.running:
            try:
                # Clean up any existing connection first
                self._cleanup_connection()
                
                # Create new connection (without unsupported timeout parameter)
                self.td_app = TD(self.username, self.password,
                               live_port=8082,
                               historical_api=False)
                
                # Start live data with retry logic
                self._start_live_data_with_retry()
                
                # Initialize data structures
                self._initialize_data_structures()
                
                # Start processing thread
                self.running = True
                self.thread = threading.Thread(target=self._run_feed, daemon=True)
                self.thread.start()
                
                self.message_queue.put(("toast", "Data feed started!", "✅"))
                
            except Exception as e:
                self._handle_start_error(e)

    def _cleanup_connection(self):
        """Ensure clean disconnection before new connection"""
        if self.td_app is not None:
            try:
                self.td_app.stop_live_data(self.req_ids)
                self.td_app.disconnect()
            except Exception as e:
                print(f"Cleanup warning: {str(e)}")
            finally:
                self.td_app = None
                time.sleep(1)  # Brief cooldown period

    def _start_live_data_with_retry(self, max_retries=3):
        """Handle connection retries with backoff"""
        for attempt in range(max_retries):
            try:
                self.req_ids = self.td_app.start_live_data(self.symbols)
                time.sleep(1)  # Allow time for subscription to establish
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

    def _initialize_data_structures(self):
        """Initialize data tracking structures"""
        self.live_data_objs = {}
        for req_id in self.req_ids:
            self.live_data_objs[req_id] = deepcopy(self.td_app.live_data[req_id])

    def _handle_start_error(self, error):
        """Centralized error handling for start_feed"""
        error_msg = str(error)
        if "User Already Connected" in error_msg:
            self.message_queue.put(("error", "Connection already exists. Try stopping first."))
        else:
            self.message_queue.put(("error", f"Failed to start feed: {error_msg}"))
        
        self.running = False
        self._cleanup_connection()

    def stop_feed(self):
        """Gracefully stop the feed with proper cleanup"""
        if self.running:
            self.running = False
            try:
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=5)
                    
                self._cleanup_connection()
                
                # Reset all state
                self.req_ids = []
                self.live_data_objs = {}
                self.message_queue.put(("toast", "Data feed stopped", "⏹️"))
                
            except Exception as e:
                self.message_queue.put(("error", f"Error stopping feed: {str(e)}"))

    def _run_feed(self):
        """Main feed processing loop with reconnection logic"""
        while self.running:
            try:
                if not self._is_connection_healthy():
                    self._handle_connection_loss()
                    continue
                    
                self._process_live_data()
                time.sleep(0.1)
                
            except Exception as e:
                self._handle_feed_error(e)

    def _is_connection_healthy(self):
        """Check if connection is still valid"""
        return self.running

    def _handle_connection_loss(self):
        """Attempt to reconnect if connection is lost"""
        self.message_queue.put(("warning", "Connection lost, attempting to reconnect..."))
        try:
            self._cleanup_connection()
            self.start_feed()
            time.sleep(5)  # Wait before retrying
        except Exception as e:
            self.message_queue.put(("error", f"Reconnection failed: {str(e)}"))

    def _process_live_data(self):
        """Process incoming live data"""
        for req_id in self.req_ids:
            current_data = self.td_app.live_data[req_id]
            if current_data != self.live_data_objs[req_id]:
                self._process_data(current_data)
                self.live_data_objs[req_id] = deepcopy(current_data)

    def _process_data(self, tick_data):
        try:
            symbol = tick_data.symbol
            price = tick_data.ltp if hasattr(tick_data, 'ltp') else None
            timestamp = tick_data.timestamp if hasattr(tick_data, 'timestamp') else datetime.now(timezone.utc)
            volume = tick_data.ttq if hasattr(tick_data, 'ttq') else 0
            
            # Ensure timestamp is timezone-aware (UTC)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                
            db_data = {
                'symbol': symbol,
                'ts': timestamp,
                'ltp': price,
                'volume': volume
            }
            self.data_queue.put(db_data)
            
        except Exception as e:
            self.message_queue.put(("error", f"Data processing failed: {str(e)}"))

    def process_messages(self):
        """Process any pending UI messages from background thread"""
        while not self.message_queue.empty():
            msg_type, *content = self.message_queue.get_nowait()
            if msg_type == "toast":
                st.toast(content[0], icon=content[1])
            elif msg_type == "error":
                st.error(content[0])
            elif msg_type == "warning":
                st.warning(content[0])

    def process_queue(self):
        """Process all items currently in the queue"""
        while not self.data_queue.empty():
            try:
                data = self.data_queue.get_nowait()
                self._store_data(data)
            except queue.Empty:
                break

    def _store_data(self, data):
        """Store data in PostgreSQL"""
        query = """
            INSERT INTO truedata_realtime 
            (symbol, ts, ltp, volume)
            VALUES (%(symbol)s, %(ts)s, %(ltp)s, %(volume)s)
            ON CONFLICT (symbol, ts) DO NOTHING
        """
        try:
            DatabaseManager.execute_query(query, data)
        except Exception as e:
            self.message_queue.put(("error", f"Database error: {str(e)}"))

    def get_active_symbols(self):
        """Returns list of currently active symbols"""
        return [self.td_app.live_data[req_id].symbol for req_id in self.req_ids] if self.td_app else []