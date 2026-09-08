with positions as (

    select
        position_date as trade_date,
        security_id,
        symbol,
        configuration_id,
        strategy_id,
        target_weight
    from {{ ref('portfolio_positions_v2') }}

),

previous_weights as (

    select
        trade_date,
        security_id,
        symbol,
        configuration_id,
        strategy_id,
        target_weight,

        lag(target_weight) over (
            partition by configuration_id, security_id
            order by trade_date
        ) as previous_weight

    from positions

),

turnover as (

    select
        trade_date,
        security_id,
        symbol,
        configuration_id,
        strategy_id,
        target_weight,
        coalesce(previous_weight, 0) as previous_weight,

        abs(
            target_weight - coalesce(previous_weight, 0)
        ) as weight_change

    from previous_weights

)

select
    trade_date,
    configuration_id,
    strategy_id,
    sum(weight_change) / 2.0 as portfolio_turnover

from turnover

group by
    trade_date,
    configuration_id,
    strategy_id

order by
    trade_date,
    configuration_id
