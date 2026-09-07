with market_prices as (

    select
        trade_date,
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

    from {{ source('raw', 'market_prices') }}

),

security_master as (

    select
        security_id,
        symbol,
        exchange

    from {{ source('raw', 'security_master') }}

)

select
    mp.trade_date,
    sm.security_id,
    mp.symbol,
    mp.exchange,

    mp.open,
    mp.high,
    mp.low,
    mp.close,
    mp.adjusted_close,
    mp.volume,

    mp.source,
    mp.ingestion_timestamp

from market_prices mp

left join security_master sm
    on mp.symbol = sm.symbol
    and mp.exchange = sm.exchange
