CREATE TABLE raw.market_prices (

    trade_date DATE NOT NULL,

    symbol VARCHAR(30) NOT NULL,

    exchange VARCHAR(20) NOT NULL,

    open NUMERIC(18,4),

    high NUMERIC(18,4),

    low NUMERIC(18,4),

    close NUMERIC(18,4),

    adjusted_close NUMERIC(18,4),

    volume BIGINT,

    source VARCHAR(100),

    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (
        trade_date,
        symbol,
        exchange
    )
);

CREATE TABLE raw.company_master (

    symbol VARCHAR(30) PRIMARY KEY,

    company_name VARCHAR(255),

    exchange VARCHAR(20),

    sector VARCHAR(100),

    industry VARCHAR(150),

    isin VARCHAR(20),

    listing_date DATE,

    active_flag BOOLEAN DEFAULT TRUE,

    source VARCHAR(100),

    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE raw.trading_calendar (

    trade_date DATE PRIMARY KEY,

    exchange VARCHAR(20),

    is_trading_day BOOLEAN,

    holiday_name VARCHAR(255)
);
CREATE TABLE metadata.ingestion_log (

    ingestion_id BIGSERIAL PRIMARY KEY,

    dataset_name VARCHAR(100),

    source VARCHAR(100),

    ingestion_start TIMESTAMP,

    ingestion_end TIMESTAMP,

    rows_received BIGINT,

    rows_inserted BIGINT,

    rows_rejected BIGINT,

    status VARCHAR(30),

    error_message TEXT
);
CREATE TABLE IF NOT EXISTS raw.security_master (
    security_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL,
    company_name VARCHAR(200),
    isin VARCHAR(20),
    exchange VARCHAR(20) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(150),
    listing_date DATE,
    delisting_date DATE,
    active_flag BOOLEAN DEFAULT TRUE,
    source VARCHAR(100),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_security_symbol_exchange
        UNIQUE (symbol, exchange)
);
