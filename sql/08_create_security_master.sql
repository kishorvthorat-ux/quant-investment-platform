CREATE TABLE IF NOT EXISTS metadata.security_master (
    security_id       BIGINT PRIMARY KEY,
    market_id         VARCHAR(30) NOT NULL,
    symbol            VARCHAR(30) NOT NULL,
    company_name      VARCHAR(255) NOT NULL,
    isin              VARCHAR(20),
    exchange_symbol   VARCHAR(30),
    sector            VARCHAR(100),
    industry          VARCHAR(150),
    listing_date      DATE,
    delisting_date    DATE,
    active_flag       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_security_market
        FOREIGN KEY (market_id)
        REFERENCES metadata.market_master(market_id),

    CONSTRAINT uq_security_market_symbol
        UNIQUE (market_id, symbol)
);
