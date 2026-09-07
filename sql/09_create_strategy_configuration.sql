CREATE TABLE IF NOT EXISTS analytics.strategy_config_version (

    configuration_id BIGSERIAL PRIMARY KEY,

    strategy_id VARCHAR(50) NOT NULL,

    configuration_version INTEGER NOT NULL,

    strategy_name VARCHAR(200) NOT NULL,
    momentum_weight NUMERIC(6,4) NOT NULL,
    risk_weight NUMERIC(6,4) NOT NULL,
    drawdown_weight NUMERIC(6,4) NOT NULL,
    trend_weight NUMERIC(6,4) NOT NULL,
    top_n INTEGER NOT NULL,
    position_weight NUMERIC(6,4) NOT NULL,
    transaction_cost_rate NUMERIC(10,6) NOT NULL,
    signal_frequency VARCHAR(30) NOT NULL,
    entry_rule VARCHAR(100) NOT NULL,
    rebalance_rule VARCHAR(100) NOT NULL,
    configuration_type VARCHAR(30) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    CONSTRAINT uq_strategy_config_version
        UNIQUE (strategy_id, configuration_version),

    CONSTRAINT chk_strategy_config_version_positive
        CHECK (configuration_version > 0),

    CONSTRAINT chk_strategy_config_version_status
        CHECK (status IN ('DRAFT', 'VALIDATED', 'FROZEN', 'RETIRED')),

    CONSTRAINT fk_strategy_config_version_strategy
        FOREIGN KEY (strategy_id)
        REFERENCES analytics.strategy_config(strategy_id)
);
