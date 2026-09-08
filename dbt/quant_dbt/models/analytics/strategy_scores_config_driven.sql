{{ config(materialized='table') }}

with ranked_features as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        factor_group_id,
        feature_id,
        feature_weight,
        direction,
        feature_value,

        percent_rank() over (
            partition by strategy_id, trade_date, feature_id
            order by feature_value
        ) as feature_rank

    from {{ ref('strategy_feature_values') }}

),

scored_features as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        factor_group_id,
        feature_id,
        feature_weight,
        direction,
        feature_value,
        feature_rank,

        case
            when direction = 'POSITIVE'
                then feature_rank
            when direction = 'NEGATIVE'
                then 1 - feature_rank
        end * feature_weight as weighted_feature_score

    from ranked_features

),

group_scores as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        factor_group_id,

        sum(weighted_feature_score) as factor_group_score

    from scored_features

    group by
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,
        factor_group_id

),

strategy_scores as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id,

        sum(factor_group_score) as composite_score

    from group_scores

    group by
        trade_date,
        security_id,
        symbol,
        exchange,
        configuration_id,
        strategy_id

)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    composite_score

from strategy_scores
