select
    trade_date,
    security_id,
    symbol,
    exchange,

    open,
    high,
    low,
    close,
    adjusted_close,
    volume,

    source,
    ingestion_timestamp

from {{ ref('stg_market_prices') }}
