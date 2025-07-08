import streamlit as st
import pandas as pd
import plotly.express as px
from configparser import ConfigParser
from database import DatabaseManager
from truedata_feed import TrueDataFeed

# Constants
SYMBOLS = [
    "NIFTY 50", "NIFTY BANK", "MCXCOMPDEX", "AARTIIND", "BRITANNIA",
    "COLPAL", "DMART", "EICHERMOT", "GILLETTE", "HDFCBANK", "ICICIBANK",
    "JKTYRE", "KAJARIACER", "LICHSGFIN", "MINDTREE", "OFSS", "PNB",
    "QUICKHEAL", "RELIANCE", "SBIN", "TCS", "UJJIVAN", "WIPRO", "YESBANK",
    "ZEEL", "NIFTY31JulFUT", "NIFTY-I", "BANKNIFTY-I", "CRUDEOIL-I",
    "GOLDM-I", "SILVERM-I", "COPPER-I", "SILVER-I"
]

# PAGE CONFIG
st.set_page_config(
    page_title="TrueData Market Dashboard",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded"
)

def clear_data_feed():
    """Ensure clean feed shutdown when session ends"""
    if 'data_feed' in st.session_state:
        if hasattr(st.session_state.data_feed, 'running') and st.session_state.data_feed.running:
            st.session_state.data_feed.stop_feed()
        del st.session_state.data_feed

@st.cache_data(ttl=1)  # Cache for 1 second
def get_recent_data(symbols, hours=24):
    """Fetch recent data with proper timezone handling"""
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

def display_current_prices(df):
    """Display current prices in a grid"""
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

def display_charts(df):
    """Display individual price charts"""
    cols = st.columns(2)
    for i, symbol in enumerate(SYMBOLS):
        with cols[i % 2]:
            st.subheader(symbol)
            symbol_df = df[df['symbol'] == symbol].copy() if not df.empty else pd.DataFrame()
            
            if not symbol_df.empty:
                if len(symbol_df) > 10:
                    symbol_df.loc[:, 'MA_10'] = symbol_df['ltp'].rolling(10).mean()
                
                fig = px.line(symbol_df, x='ts', y='ltp',
                            labels={'ts': 'Time', 'ltp': 'Price'},
                            height=300)
                
                if 'MA_10' in symbol_df.columns:
                    fig.add_scatter(
                        x=symbol_df['ts'], 
                        y=symbol_df['MA_10'], 
                        name='10-period MA',
                        line=dict(color='orange', width=2)
                    )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.line(title="No data")
                st.plotly_chart(fig, use_container_width=True)

def main():
    # Initialize database pool and tables
    DatabaseManager.initialize()

    # Load config and initialize feed
    config = ConfigParser()
    config.read('config.ini')

    # Register cleanup handler
    if 'cleanup_registered' not in st.session_state:
        st.session_state.cleanup_registered = True
        import atexit
        atexit.register(clear_data_feed)
    
    # Initialize feed only if it doesn't exist or needs reset
    if 'data_feed' not in st.session_state or not hasattr(st.session_state.data_feed, 'running'):
        config = ConfigParser()
        config.read('config.ini')
        st.session_state.data_feed = TrueDataFeed(
            username=config['truedata']['username'],
            password=config['truedata']['password'],
            symbols=SYMBOLS
        )
        st.session_state.feed_running = False
    
    # UI Layout
    st.title("📊 TrueData Real-Time Market Dashboard")
    
    # Control Panel
    with st.sidebar:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶ Start Feed", disabled=st.session_state.feed_running):
                try:
                    st.session_state.data_feed.start_feed()
                    st.session_state.feed_running = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Start failed: {str(e)}")
                    st.session_state.feed_running = False
        
        with col2:
            if st.button("⏹ Stop Feed", disabled=not st.session_state.feed_running):
                st.session_state.data_feed.stop_feed()
                st.session_state.feed_running = False
                st.rerun()
                time.sleep(1)  # Ensure clean state before allowing restart
        
        st.divider()
        status_color = "red" if not st.session_state.feed_running else "green"
        st.markdown(f"**Status:** <span style='color:{status_color}'>"
                   f"{'Running' if st.session_state.feed_running else 'Stopped'}</span>",
                   unsafe_allow_html=True)
        
        # Debug info
        with st.expander("Connection Status"):
            if st.session_state.feed_running:
                status = "Connected" if st.session_state.data_feed.running else "Disconnected"
                st.write(f"Status: {status}")
                if hasattr(st.session_state.data_feed, 'req_ids'):
                    st.write(f"Active symbols: {len(st.session_state.data_feed.req_ids)}")
            else:
                st.write("Status: Stopped")

    # Process any messages from background thread
    if 'data_feed' in st.session_state:
        st.session_state.data_feed.process_messages()
    
    # Process data queue if feed is running
    if st.session_state.feed_running and 'data_feed' in st.session_state:
        st.session_state.data_feed.process_queue()
    
    # Get data for ALL symbols
    df = get_recent_data(SYMBOLS, hours=4)  # Last 4 hours for all symbols
    
    # Create tabs
    tab1, tab2 = st.tabs(["Current Prices", "Price Charts"])
    
    with tab1:
        st.header("Current Market Prices")
        display_current_prices(df)
    
    with tab2:
        st.header("Price Charts")
        display_charts(df)
    
    # Auto-refresh only when feed is running
    if st.session_state.feed_running:
        st.rerun()

if __name__ == "__main__":
    main()