CREATE TABLE IF NOT EXISTS metadata.data_source (
    source_id        VARCHAR(50) PRIMARY KEY,
    source_name      VARCHAR(100) NOT NULL,
    source_type      VARCHAR(50) NOT NULL,
    market_id        VARCHAR(30),
    priority         INTEGER NOT NULL DEFAULT 1,
    active_flag      BOOLEAN NOT NULL DEFAULT TRUE,
    description      VARCHAR(500),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_source_market
        FOREIGN KEY (market_id)
        REFERENCES metadata.market_master(market_id),

    CONSTRAINT chk_source_priority
        CHECK (priority > 0)
);
