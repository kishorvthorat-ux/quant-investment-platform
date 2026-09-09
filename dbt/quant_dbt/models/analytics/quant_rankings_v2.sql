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

configurations as (

    select
        configuration_id,
        top_n

    from {{ source('analytics', 'strategy_config_version') }}

    where status in ('VALIDATED', 'FROZEN')

),

ranked as (

    select
        s.*,
        row_number() over (
            partition by s.configuration_id, s.trade_date
            order by s.composite_score desc, s.symbol
        ) as rank

    from scores s

)

select
    r.trade_date,
    r.security_id,
    r.symbol,
    r.exchange,
    r.configuration_id,
    r.strategy_id,
    r.composite_score,
    r.rank,

    case
        when r.rank <= c.top_n then true
        else false
    end as selected_flag

from ranked r

inner join configurations c
    on r.configuration_id = c.configuration_id
