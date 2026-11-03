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

signal_schedule as (

    select
        configuration_id,
        strategy_id,
        signal_frequency,
        signal_date,
        previous_signal_date
    from {{ ref('strategy_signal_schedule_v2') }}

),

current_selected as (

    select
        s.signal_date,
        s.previous_signal_date,
        s.signal_frequency,
        w.security_id,
        w.symbol,
        w.exchange,
        w.configuration_id,
        w.strategy_id,
        w.rank as current_rank,
        w.composite_score as current_composite_score,
        w.target_weight as current_weight
    from signal_schedule s
    inner join weights w
        on w.signal_date = s.signal_date
       and w.configuration_id = s.configuration_id
       and w.strategy_id = s.strategy_id
    where w.selected_flag = true

),

previous_selected as (

    select
        s.signal_date,
        s.previous_signal_date,
        s.signal_frequency,
        s.configuration_id,
        s.strategy_id,
        w.security_id,
        w.symbol,
        w.exchange,
        w.rank as previous_rank,
        w.target_weight as previous_weight
    from signal_schedule s
    inner join weights w
        on w.signal_date = s.previous_signal_date
       and w.configuration_id = s.configuration_id
       and w.strategy_id = s.strategy_id
    where w.selected_flag = true

),

portfolio_changes as (

    select
        coalesce(c.signal_date, p.signal_date) as signal_date,
        coalesce(c.previous_signal_date, p.previous_signal_date)
            as previous_signal_date,
        coalesce(c.signal_frequency, p.signal_frequency) as signal_frequency,
        coalesce(c.security_id, p.security_id) as security_id,
        coalesce(c.symbol, p.symbol) as symbol,
        coalesce(c.exchange, p.exchange) as exchange,
        coalesce(c.configuration_id, p.configuration_id) as configuration_id,
        coalesce(c.strategy_id, p.strategy_id) as strategy_id,
        p.previous_rank,
        c.current_rank,
        p.previous_weight,
        coalesce(c.current_weight, 0.0) as current_weight,
        c.current_composite_score
    from current_selected c
    full outer join previous_selected p
        on c.signal_date = p.signal_date
       and c.security_id = p.security_id
       and c.configuration_id = p.configuration_id
       and c.strategy_id = p.strategy_id

),

trading_dates as (

    select trade_date
    from {{ ref('stg_trading_calendar') }}
    where is_trading_day = true

),

with_execution_date as (

    select
        pc.*,
        (
            select min(td.trade_date)
            from trading_dates td
            where td.trade_date > pc.signal_date
        ) as execution_date
    from portfolio_changes pc

)

select
    signal_date,
    execution_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    signal_frequency,
    previous_signal_date,
    previous_rank,
    current_rank,
    previous_weight,
    current_weight,
    current_composite_score,
    case
        when coalesce(previous_weight, 0.0) = 0.0
             and current_weight > 0.0
            then 'BUY'
        when previous_weight > 0.0
             and current_weight > 0.0
            then 'HOLD'
        when previous_weight > 0.0
             and current_weight = 0.0
            then 'SELL'
    end as signal
from with_execution_date
where
    (coalesce(previous_weight, 0.0) > 0.0)
    or
    (current_weight > 0.0)
