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


CREATE TABLE IF NOT EXISTS analytics.strategy_config_version_factor_group (

    configuration_id BIGINT NOT NULL,

    factor_group_id VARCHAR(50) NOT NULL,
    factor_group_name VARCHAR(100) NOT NULL,
    group_weight NUMERIC(18,6) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_strategy_config_version_factor_group
        PRIMARY KEY (configuration_id, factor_group_id),

    CONSTRAINT chk_strategy_config_version_factor_group_weight
        CHECK (group_weight >= 0),

    CONSTRAINT fk_strategy_config_version_factor_group_configuration
        FOREIGN KEY (configuration_id)
        REFERENCES analytics.strategy_config_version(configuration_id)
);


CREATE TABLE IF NOT EXISTS analytics.strategy_config_version_factor (

    configuration_id BIGINT NOT NULL,

    factor_group_id VARCHAR(50) NOT NULL,
    feature_id VARCHAR(50) NOT NULL,
    feature_weight NUMERIC(18,6) NOT NULL DEFAULT 0,
    direction VARCHAR(10) NOT NULL DEFAULT 'POSITIVE',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_strategy_config_version_factor
        PRIMARY KEY (configuration_id, factor_group_id, feature_id),

    CONSTRAINT chk_strategy_config_version_factor_weight
        CHECK (feature_weight >= 0),

    CONSTRAINT chk_strategy_config_version_factor_direction
        CHECK (direction IN ('POSITIVE', 'NEGATIVE')),

    CONSTRAINT fk_strategy_config_version_factor_group
        FOREIGN KEY (configuration_id, factor_group_id)
        REFERENCES analytics.strategy_config_version_factor_group(
            configuration_id,
            factor_group_id
        ),

    CONSTRAINT fk_strategy_config_version_factor_feature
        FOREIGN KEY (feature_id)
        REFERENCES metadata.feature_catalog(feature_id)
);
