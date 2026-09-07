with signal_dates as (

    select
        trade_date as signal_date,
        lead(trade_date) over (
            order by trade_date
        ) as next_signal_date

    from (
        select distinct trade_date
        from {{ ref('portfolio_weights_monthly') }}
    ) d

),

monthly_signals as (

    select
        w.trade_date as signal_date,
        w.security_id,
        w.symbol,
        w.exchange,
        w.rank,
        w.composite_score,
        w.selected_flag,
        w.target_weight,
        s.next_signal_date

    from {{ ref('portfolio_weights_monthly') }} w

    inner join signal_dates s
        on w.trade_date = s.signal_date

),

trading_dates as (

    select
        trade_date

    from {{ ref('stg_trading_calendar') }}

    where is_trading_day = true

),

daily_positions as (

    select
        s.signal_date,
        td.trade_date as position_date,
        s.security_id,
        s.symbol,
        s.exchange,
        s.rank,
        s.composite_score,
        s.selected_flag,
        s.target_weight

    from monthly_signals s

    inner join trading_dates td

        on td.trade_date > s.signal_date

        and (
            s.next_signal_date is null
            or td.trade_date < s.next_signal_date
        )

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

from daily_positions

order by
    position_date,
    security_id
