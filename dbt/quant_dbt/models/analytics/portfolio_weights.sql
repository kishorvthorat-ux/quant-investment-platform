with rankings as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag
    from {{ ref('quant_rankings') }}

),

portfolio as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag,

        case
            when selected_flag = true then 1.0 / 2
            else 0.0
        end as target_weight

    from rankings

)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    rank,
    composite_score,
    selected_flag,
    target_weight

from portfolio
