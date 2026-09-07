with weights as (

    select
        trade_date as signal_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag,
        target_weight

    from {{ ref('portfolio_weights') }}

),

trading_dates as (

    select
        trade_date,
        lead(trade_date) over (
            order by trade_date
        ) as next_trade_date

    from {{ ref('stg_trading_calendar') }}

    where is_trading_day = true

),

positions as (

    select
        w.signal_date,
        td.next_trade_date as position_date,
        w.security_id,
        w.symbol,
        w.exchange,
        w.rank,
        w.composite_score,
        w.selected_flag,
        w.target_weight

    from weights w

    left join trading_dates td
        on w.signal_date = td.trade_date

)

select
    signal_date,
    position_date,
    security_id,
    symbol,
    exchange,
    rank,
    composite_score,
    selected_flag,
    target_weight

from positions
where position_date is not null
