import streamlit as st
import pandas as pd
import plotly.express as px
from configparser import ConfigParser
from database import DatabaseManager
from truedata_feed import TrueDataFeed
from datetime import datetime
import time
import random

# Constants
SYMBOLS = ["NIFTY 50","NIFTY BANK","MCXCOMPDEX","AARTIIND","BRITANNIA",
"COLPAL","DMART","EICHERMOT","GILLETTE","HDFCBANK","ICICIBANK","JKTYRE","KAJARIACER",
"LICHSGFIN","MINDTREE","OFSS","PNB","QUICKHEAL","RELIANCE","SBIN","TCS","UJJIVAN",
"WIPRO","YESBANK","ZEEL","NIFTY31JulFUT", "NIFTY-I","BANKNIFTY-I","CRUDEOIL-I","GOLDM-I","SILVERM-I","COPPER-I", "SILVER-I"]

# PAGE CONFIG
st.set_page_config(
    page_title="TrueData Market Dashboard",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded"
)

@st.cache_data(ttl=1)
def get_recent_data(symbols, hours=24):
    """Fetch recent data"""
    if not symbols:
        return pd.DataFrame(columns=['symbol', 'ts', 'ltp'])
        
    query = """
        SELECT symbol, ts AT TIME ZONE 'UTC' as ts, ltp 
        FROM truedata_realtime 
        WHERE symbol = ANY(%s) 
        AND ts >= NOW() - INTERVAL '%s hours'
        ORDER BY ts
    """
    try:
        results = DatabaseManager.execute_query(query, (symbols, hours))
        if results:
            df = pd.DataFrame(results, columns=['symbol', 'ts', 'ltp'])
            df['ts'] = pd.to_datetime(df['ts'])
            return df
        return pd.DataFrame(columns=['symbol', 'ts', 'ltp'])
    except Exception as e:
        st.error(f"Data fetch error: {str(e)}")
        return pd.DataFrame(columns=['symbol', 'ts', 'ltp'])

def create_ui(df, update_counter):
    """Create the complete UI inside the placeholder"""
    # Create tabs
    tab1, tab2 = st.tabs(["Current Prices", "Price Charts"])
    
    with tab1:
        st.header("Current Market Prices")
        current_prices = {}
        if not df.empty:
            latest_data = df.sort_values('ts').groupby('symbol').last().reset_index().copy()
            current_prices = latest_data.set_index('symbol')['ltp'].to_dict()
        
        cols = st.columns(4)
        for i, symbol in enumerate(SYMBOLS):
            with cols[i % 4]:
                price = current_prices.get(symbol, None)
                if price is not None:
                    symbol_df = df[df['symbol'] == symbol].copy()
                    if len(symbol_df) > 1:
                        prev_price = symbol_df.iloc[-2]['ltp']
                        delta = price - prev_price
                        delta_pct = (delta / prev_price) * 100
                        st.metric(
                            label=symbol,
                            value=f"{price:.2f}",
                            delta=f"{delta:.2f} ({delta_pct:.2f}%)"
                        )
                    else:
                        st.metric(label=symbol, value=f"{price:.2f}")
                else:
                    st.metric(label=symbol, value="N/A")
    
    with tab2:
        st.header("Price Charts")
        cols = st.columns(2)
        for i, symbol in enumerate(SYMBOLS):
            with cols[i % 2]:
                symbol_df = df[df['symbol'] == symbol].copy() if not df.empty else pd.DataFrame()
                
                if not symbol_df.empty:
                    if len(symbol_df) > 10:
                        symbol_df.loc[:, 'MA_10'] = symbol_df['ltp'].rolling(10).mean()
                    
                    fig = px.line(symbol_df, x='ts', y='ltp',
                                labels={'ts': 'Time', 'ltp': 'Price'},
                                title=f"{symbol}",
                                height=300)
                    
                    if 'MA_10' in symbol_df.columns:
                        fig.add_scatter(
                            x=symbol_df['ts'], 
                            y=symbol_df['MA_10'], 
                            name='10-period MA',
                            line=dict(color='orange', width=2)
                        )
                    
                    fig.update_layout(
                        height=300,
                        margin=dict(l=20, r=20, t=50, b=20),
                        showlegend=True,
                        title_x=0.5
                    )
                    st.plotly_chart(
                        fig, 
                        use_container_width=True,
                        key=f"chart_{symbol}_{update_counter}_{random.random()}"
                    )
                else:
                    fig = px.line(title=f"{symbol} - No data available")
                    fig.update_layout(
                        height=300,
                        margin=dict(l=20, r=20, t=50, b=20),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=False),
                        title_x=0.5
                    )
                    st.plotly_chart(
                        fig, 
                        use_container_width=True,
                        key=f"empty_chart_{symbol}_{update_counter}_{random.random()}"
                    )

def main():
    # Initialize database
    DatabaseManager.initialize()

    # Load config
    config = ConfigParser()
    config.read('config.ini')
    
    # Initialize all session state variables
    if 'data_feed' not in st.session_state:
        st.session_state.data_feed = TrueDataFeed(
            username=config['truedata']['username'],
            password=config['truedata']['password'],
            symbols=SYMBOLS
        )
        st.session_state.processing_active = False
        st.session_state.connection_active = False
        st.session_state.last_update = 0
        st.session_state.update_counter = 0
        st.session_state.placeholder = st.empty()

    # Control Panel in Sidebar
    with st.sidebar:
        # Connection controls
        st.markdown("**Connection Controls**")
        col1, col2 = st.columns(2)
        with col1:
            connect_btn = st.button("🔌 Connect",
                                 disabled=st.session_state.connection_active, 
                                 use_container_width=True)
        with col2:
            disconnect_btn = st.button("🚫 Disconnect",
                                    disabled=not st.session_state.connection_active, 
                                    use_container_width=True)
        
        # Processing controls
        col3, col4 = st.columns(2)
        with col3:
            start_btn = st.button("▶ Start Processing", 
                                disabled=st.session_state.processing_active or not st.session_state.connection_active,
                                key="start_btn",
                                use_container_width=True) 
        with col4:
            stop_btn = st.button("⏹ Stop Processing", 
                                disabled=not st.session_state.processing_active,
                                key="stop_btn",
                                use_container_width=True)
        
        st.divider()
        
        # Status indicators
        connection_status = "✅ Connected" if st.session_state.connection_active else "⚠️ Disconnected"
        st.markdown(f"**Connection Status:** {connection_status}")
        
        status_color = "green" if st.session_state.processing_active else "gray"
        status_text = "▶ Processing" if st.session_state.processing_active else "⏹ Stopped"
        st.markdown(f"**Processing Status:** <span style='color:{status_color}'>{status_text}</span>",
                   unsafe_allow_html=True)
        
        if st.session_state.connection_active:
            st.write(f"Active symbols: {len(st.session_state.data_feed.get_active_symbols())}")

    # Handle button actions
    if connect_btn:
        if st.session_state.data_feed.connection():
            st.session_state.connection_active = True
            st.rerun()

    if disconnect_btn:
        st.session_state.data_feed.disconnection()
        st.session_state.connection_active = False
        st.session_state.processing_active = False
        st.rerun()

    if start_btn:
        if st.session_state.data_feed.start_processing():
            st.session_state.processing_active = True
            st.session_state.last_update = 0
            st.session_state.update_counter = 0
            st.rerun()  

    if stop_btn:
        st.session_state.data_feed.stop_processing()
        st.session_state.processing_active = False
        st.rerun() 

    # Process UI messages
    st.session_state.data_feed.process_messages()

    # Main title (outside the placeholder so it doesn't refresh)
    st.title("📊 TrueData Real-Time Market Dashboard")

    # Initial data load
    df = get_recent_data(SYMBOLS, hours=4)
    
    # Main UI update loop
    while True:
        # Update the entire UI inside the placeholder

        if st.session_state.connection_active == False:
            st.session_state.data_feed.disconnection()

        with st.session_state.placeholder.container():
            create_ui(df, st.session_state.update_counter)

        # If processing is active, check for updates
        if st.session_state.processing_active:
            current_time = time.time()
            
            # Update every 1 second
            if current_time - st.session_state.last_update >= 1.0:
                # Get fresh data
                df = get_recent_data(SYMBOLS, hours=4)

                # Increment counter for unique chart keys
                st.session_state.update_counter += 1
                
                # Process any new data
                st.session_state.data_feed.check_for_updates()
                st.session_state.data_feed.process_queue()
                
                # Update last update time
                st.session_state.last_update = current_time
        
        # Small sleep to prevent CPU overload
        time.sleep(10)

if __name__ == "__main__":
    main()