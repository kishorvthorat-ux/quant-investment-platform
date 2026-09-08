with scores as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        composite_score

    from {{ ref('strategy_scores_config_driven') }}

),

ranked as (

    select
        *,
        row_number() over (
            partition by configuration_id, trade_date
            order by composite_score desc, symbol
        ) as rank

    from scores

)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    composite_score,
    rank,

    case
        when rank <= {{ var('top_n', 2) }} then true
        else false
    end as selected_flag

from ranked
