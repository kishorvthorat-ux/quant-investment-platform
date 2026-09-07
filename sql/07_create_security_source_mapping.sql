CREATE TABLE IF NOT EXISTS metadata.security_source_mapping (
    source_id       VARCHAR(50) NOT NULL,
    security_id     BIGINT NOT NULL,
    source_symbol   VARCHAR(100) NOT NULL,
    valid_from      DATE NOT NULL,
    valid_to        DATE,
    active_flag     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source_id, source_symbol, valid_from),

    CONSTRAINT fk_mapping_source
        FOREIGN KEY (source_id)
        REFERENCES metadata.data_source(source_id),

    CONSTRAINT chk_mapping_dates
        CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
