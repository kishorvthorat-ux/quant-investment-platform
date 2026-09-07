INSERT INTO raw.security_master
    (symbol, company_name, exchange, source)
VALUES
    ('RELIANCE', 'Reliance Industries Limited', 'NSE', 'Yahoo Finance'),
    ('TCS', 'Tata Consultancy Services Limited', 'NSE', 'Yahoo Finance'),
    ('HDFCBANK', 'HDFC Bank Limited', 'NSE', 'Yahoo Finance'),
    ('INFY', 'Infosys Limited', 'NSE', 'Yahoo Finance'),
    ('ICICIBANK', 'ICICI Bank Limited', 'NSE', 'Yahoo Finance')
ON CONFLICT (symbol, exchange) DO NOTHING;
