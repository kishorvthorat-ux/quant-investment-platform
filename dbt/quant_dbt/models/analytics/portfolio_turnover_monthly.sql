with positions as (

    select
        position_date as trade_date,
        security_id,
        target_weight

    from {{ ref('portfolio_positions_monthly') }}

),

changes as (

    select
        trade_date,
        security_id,
        target_weight,

        lag(target_weight) over (
            partition by security_id
            order by trade_date
        ) as previous_weight

    from positions

)

select
    trade_date,

    sum(
        abs(
            target_weight
            - coalesce(previous_weight, 0)
        )
    ) / 2.0 as portfolio_turnover

from changes

group by trade_date
order by trade_date
