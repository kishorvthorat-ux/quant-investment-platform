with weights as (

    select
        trade_date as signal_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        rank,
        composite_score,
        selected_flag,
        target_weight
    from {{ ref('portfolio_weights_v2') }}

),

weekly_signal_dates as (

    select
        configuration_id,
        strategy_id,
        date_trunc('week', signal_date) as signal_week,
        max(signal_date) as signal_date
    from weights
    group by
        configuration_id,
        strategy_id,
        date_trunc('week', signal_date)

),

signal_schedule as (

    select
        configuration_id,
        strategy_id,
        signal_date,
        lead(signal_date) over (
            partition by configuration_id, strategy_id
            order by signal_date
        ) as next_signal_date
    from weekly_signal_dates

),

weekly_signals as (

    select
        w.signal_date,
        s.next_signal_date,
        w.security_id,
        w.symbol,
        w.exchange,
        w.configuration_id,
        w.strategy_id,
        w.rank,
        w.composite_score,
        w.selected_flag,
        w.target_weight
    from weights w
    inner join signal_schedule s
        on w.signal_date = s.signal_date
       and w.configuration_id = s.configuration_id
       and w.strategy_id = s.strategy_id

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
        s.configuration_id,
        s.strategy_id,
        s.rank,
        s.composite_score,
        s.selected_flag,
        s.target_weight

    from weekly_signals s

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
    configuration_id,
    strategy_id,
    rank,
    composite_score,
    selected_flag,
    target_weight

from daily_positions
