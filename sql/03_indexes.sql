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
