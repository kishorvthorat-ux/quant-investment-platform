with positions as (

    select
        position_date as trade_date,
        security_id,
        symbol,
        target_weight
    from {{ ref('portfolio_positions_weekly') }}

),

previous_weights as (

    select
        trade_date,
        security_id,
        symbol,
        target_weight,

        lag(target_weight) over (
            partition by security_id
            order by trade_date
        ) as previous_weight

    from positions

),

turnover as (

    select
        trade_date,
        security_id,
        symbol,
        target_weight,

        coalesce(previous_weight, 0)
            as previous_weight,

        abs(
            target_weight
            - coalesce(previous_weight, 0)
        ) as weight_change

    from previous_weights

)

select
    trade_date,

    sum(weight_change) / 2.0
        as portfolio_turnover

from turnover

group by trade_date

order by trade_date
