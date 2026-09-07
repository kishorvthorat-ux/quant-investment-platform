with rankings as (
    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag
    from {{ ref('quant_rankings_v2') }}
)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    rank,
    composite_score,
    selected_flag,

    case
        when selected_flag = true then 0.5
        else 0.0
    end as target_weight

from rankings
