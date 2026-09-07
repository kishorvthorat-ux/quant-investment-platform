CREATE TABLE IF NOT EXISTS metadata.trading_calendar (
    calendar_id      VARCHAR(30) NOT NULL,
    market_id        VARCHAR(30) NOT NULL,
    trade_date       DATE NOT NULL,
    is_trading_day   BOOLEAN NOT NULL,
    session_open     TIME,
    session_close    TIME,
    holiday_name     VARCHAR(255),
    source           VARCHAR(100) NOT NULL,
    calendar_version VARCHAR(30),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (calendar_id, trade_date),

    CONSTRAINT fk_calendar_market
        FOREIGN KEY (market_id)
        REFERENCES metadata.market_master(market_id)
);
