# TrueData Market Dashboard

## Overview

A real-time market dashboard that displays current prices and historical charts for various financial instruments using TrueData's WebSocket API. The application stores data in PostgreSQL and provides a Streamlit-based web interface for visualization.

## Features

- Real-time price updates for multiple financial instruments
- Interactive price charts with 10-period moving averages
- Current price metrics with change indicators
- Start/Stop controls for data processing
- Connection status monitoring
- Historical data visualization (up to 24 hours)

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up PostgreSQL database:
   - Create a database named `truedata`
   - The application will automatically create the required tables on first run

4. Configure the application by editing `config.ini`:
   ```ini
   [postgresql]
   host = localhost
   database = truedata
   user = postgres
   password = your_password
   port = 5432

   [truedata]
   username = your_truedata_username
   password = your_truedata_password
   ```

## Usage

1. Run the application:
   ```bash
   streamlit run app.py
   ```

2. In the web interface:
   - Click "▶ Start Processing" to begin receiving real-time data
   - View current prices in the "Current Prices" tab
   - View historical charts in the "Price Charts" tab
   - Click "⏹ Stop Processing" to pause data collection

## Technical Details

### Components

- **app.py**: Main Streamlit application
- **database.py**: PostgreSQL connection and query management
- **truedata_feed.py**: TrueData WebSocket client and data processing
- **config.ini**: Configuration file for database and API credentials

### Data Flow

1. TrueData WebSocket client receives real-time market data
2. Data is processed and stored in PostgreSQL
3. Streamlit interface displays:
   - Current prices with change indicators
   - Interactive historical price charts
   - System status information

### Database Schema

The application uses a single table:
```sql
-- Table: public.truedata_realtime

-- DROP TABLE IF EXISTS public.truedata_realtime;

CREATE TABLE IF NOT EXISTS public.truedata_realtime
(
    symbol character varying(50) COLLATE pg_catalog."default" NOT NULL,
    ts timestamp with time zone NOT NULL,
    ltp numeric(20,4),
    volume bigint,
    CONSTRAINT truedata_realtime_pkey PRIMARY KEY (symbol, ts)
) PARTITION BY RANGE (ts);

ALTER TABLE IF EXISTS public.truedata_realtime
    OWNER to postgres;
-- Index: idx_truedata_symbol_ts

-- DROP INDEX IF EXISTS public.idx_truedata_symbol_ts;

CREATE INDEX IF NOT EXISTS idx_truedata_symbol_ts
    ON public.truedata_realtime USING btree
    (symbol COLLATE pg_catalog."default" ASC NULLS LAST, ts ASC NULLS LAST)
;

-- Partitions SQL

CREATE TABLE public.truedata_realtime_2025_07 PARTITION OF public.truedata_realtime
    FOR VALUES FROM ('2025-07-01 00:00:00+08') TO ('2025-08-01 00:00:00+08')
TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.truedata_realtime_2025_07
    OWNER to postgres;
CREATE TABLE public.truedata_realtime_2025_08 PARTITION OF public.truedata_realtime
    FOR VALUES FROM ('2025-08-01 00:00:00+08') TO ('2025-09-01 00:00:00+08')
TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.truedata_realtime_2025_08
    OWNER to postgres;
```

## Supported Symbols

The dashboard currently tracks the following instruments:
- NIFTY 50
- NIFTY BANK
- MCXCOMPDEX
- Various individual stocks (AARTIIND, BRITANNIA, etc.)
- Futures and Indices (NIFTY31JulFUT, NIFTY-I, etc.)
- Commodities (CRUDEOIL-I, GOLDM-I, etc.)

## Requirements

- Python 3.7+
- PostgreSQL 12+
- TrueData WebSocket API credentials
- Libraries listed in requirements.txt

## License

This project is provided for educational purposes. Please ensure you have proper authorization to use the TrueData API before deploying this application.