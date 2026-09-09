with rankings as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        rank,
        composite_score,
        selected_flag
    from {{ ref('quant_rankings_v2') }}

),

configurations as (

    select
        configuration_id,
        top_n,
        position_weight
    from {{ source('analytics', 'strategy_config_version') }}

    where status in ('VALIDATED', 'FROZEN')

)

select
    r.trade_date,
    r.security_id,
    r.symbol,
    r.exchange,
    r.configuration_id,
    r.strategy_id,
    r.rank,
    r.composite_score,
    r.selected_flag,

    case
        when r.selected_flag = true
            then 1.0 / c.top_n
        else 0.0
    end as target_weight

from rankings r

inner join configurations c
    on r.configuration_id = c.configuration_id
