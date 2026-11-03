with signal_schedule as (

    select
        configuration_id,
        strategy_id,
        signal_date,
        execution_date,
        next_execution_date

    from {{ ref('strategy_signal_schedule_v2') }}

),

weights as (

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

scheduled_weights as (

    select
        s.signal_date,
        s.execution_date,
        s.next_execution_date,

        w.security_id,
        w.symbol,
        w.exchange,
        w.configuration_id,
        w.strategy_id,
        w.rank,
        w.composite_score,
        w.selected_flag,
        w.target_weight

    from signal_schedule s

    inner join weights w
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

    from scheduled_weights s

    inner join trading_dates td
        on td.trade_date >= s.execution_date
       and (
            s.next_execution_date is null
            or td.trade_date < s.next_execution_date
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
