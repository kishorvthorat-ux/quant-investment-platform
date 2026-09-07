CREATE INDEX idx_market_prices_symbol
ON raw.market_prices(symbol);

CREATE INDEX idx_market_prices_date
ON raw.market_prices(trade_date);

CREATE INDEX idx_market_prices_symbol_date
ON raw.market_prices(symbol, trade_date);

CREATE INDEX idx_company_sector
ON raw.company_master(sector);

CREATE INDEX idx_company_industry
ON raw.company_master(industry);

CREATE INDEX IF NOT EXISTS idx_security_master_isin
ON raw.security_master(isin);

CREATE INDEX IF NOT EXISTS idx_security_master_sector
ON raw.security_master(sector);

CREATE INDEX IF NOT EXISTS idx_security_master_active
ON raw.security_master(active_flag);
