from truedata_ws.websocket.TD import TD
from datetime import datetime, timezone
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
        self.td_app = None
        self.req_ids = []
        self._last_data = {}
        self._processing_active = False
        self._connection_active = False

    def connection(self):
        """Establish connection to TrueData service"""
        if self._connection_active:
            return True
            
        try:
            self._cleanup_connection()
            self.td_app = TD(self.username, self.password,
                           live_port=8082,
                           historical_api=False)
            self._connection_active = True
            self.message_queue.put(("toast", "Connected to TrueData service!", "✅"))
            return True
        except Exception as e:
            self.message_queue.put(("error", f"Connection failed: {str(e)}"))
            self._cleanup_connection()
            return False

    def disconnection(self):
        """Disconnect from TrueData service"""
        if not self._connection_active:
            return
            
        self.stop_processing()
        self._cleanup_connection()
        self._connection_active = False
        self.message_queue.put(("toast", "Disconnected from TrueData service", "🔌"))

    def start_processing(self):
        """Enable data processing and storage"""
        if not self._connection_active:
            self.message_queue.put(("error", "Not connected to TrueData service"))
            return False
            
        self.req_ids = self.td_app.start_live_data(self.symbols)
        time.sleep(1)  # Allow connection to establish
        self._last_data = {
            req_id: deepcopy(self.td_app.live_data[req_id])
            for req_id in self.req_ids
        }    
        self._processing_active = True
        self.message_queue.put(("toast", "Data processing started", "▶️"))
        return True

    def stop_processing(self):
        """Disable data processing and storage"""
        if not self._processing_active:
            return
            
        self._processing_active = False
        self.td_app.stop_live_data(self.req_ids)
        self.message_queue.put(("toast", "Data processing stopped", "⏹️"))

    def _cleanup_connection(self):
        """Internal cleanup method"""
        if self.td_app is not None:
            try:
                if hasattr(self.td_app, 'live_data') and self.req_ids:
                    self.td_app.stop_live_data(self.req_ids)
                self.td_app.disconnect()
            except Exception as e:
                print(f"Cleanup warning: {str(e)}")
            finally:
                self.td_app = None
                self.req_ids = []
                time.sleep(0.5)

    def check_for_updates(self):
        """Check for new data (only processes if active)"""
        if not self.is_connected() or not self._processing_active:
            return False
            
        processed = False
        for req_id in self.req_ids:
            current_data = self.td_app.live_data[req_id]
            if current_data != self._last_data.get(req_id):
                self._process_data(current_data)
                self._last_data[req_id] = deepcopy(current_data)
                processed = True
        return processed

    def _process_data(self, tick_data):
        """Process incoming tick data"""
        try:
            symbol = tick_data.symbol
            price = getattr(tick_data, 'ltp', None)
            timestamp = getattr(tick_data, 'timestamp', datetime.now(timezone.utc))
            volume = getattr(tick_data, 'ttq', 0)
            
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                
            self.data_queue.put({
                'symbol': symbol,
                'ts': timestamp,
                'ltp': price,
                'volume': volume
            })
        except Exception as e:
            self.message_queue.put(("error", f"Data processing failed: {str(e)}"))

    def process_queue(self):
        """Process all items in queue"""
        processed = 0
        while not self.data_queue.empty():
            try:
                data = self.data_queue.get_nowait()
                self._store_data(data)
                processed += 1
            except queue.Empty:
                break
        return processed

    def _store_data(self, data):
        """Store data in PostgreSQL"""
        if not self._processing_active:
            return
            
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

    def process_messages(self):
        """Process UI messages"""
        while not self.message_queue.empty():
            msg_type, *content = self.message_queue.get_nowait()
            if msg_type == "toast":
                st.toast(content[0], icon=content[1])
            elif msg_type == "error":
                st.error(content[0])
            elif msg_type == "warning":
                st.warning(content[0])

    def is_connected(self):
        """Check if connected to feed"""
        return self.td_app is not None

    def is_processing(self):
        """Check if processing data"""
        return self._processing_active

    def get_active_symbols(self):
        """Get active symbols"""
        if self.is_connected():
            return [self.td_app.live_data[req_id].symbol for req_id in self.req_ids]
        return []