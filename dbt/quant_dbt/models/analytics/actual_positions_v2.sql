with executed_trades as (

    select
        signal_date,
        execution_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        side,
        order_weight,
        execution_price
    from {{ ref('executed_trades_v2') }}
    where execution_status in ('FILLED', 'DATA_MISSING')

),

position_changes as (

    select
        signal_date,
        execution_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        side,
        order_weight,
        execution_price,

        case
            when side = 'BUY' then order_weight
            when side = 'SELL' then -order_weight
        end as position_change

    from executed_trades

),

running_positions as (

    select
        *,
        sum(position_change) over (
            partition by configuration_id, security_id
            order by execution_date, signal_date
            rows between unbounded preceding and current row
        ) as actual_weight

    from position_changes

)

select
    execution_date as position_date,
    signal_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    side as last_trade_side,
    order_weight as last_trade_weight,
    execution_price as last_execution_price,
    position_change,
    actual_weight

from running_positions
