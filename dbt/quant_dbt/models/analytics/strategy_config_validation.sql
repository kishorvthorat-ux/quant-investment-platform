{{ config(materialized='table') }}

with group_validation as (

    select
        fg.strategy_id,
        fg.factor_group_id,
        fg.group_weight,
        coalesce(
            sum(sf.feature_weight) filter (where sf.enabled = true),
            0
        ) as feature_weight_sum

    from {{ source('analytics', 'strategy_factor_groups') }} fg

    left join {{ source('analytics', 'strategy_factors') }} sf
        on fg.strategy_id = sf.strategy_id
       and fg.factor_group_id = sf.factor_group_id

    where fg.enabled = true

    group by
        fg.strategy_id,
        fg.factor_group_id,
        fg.group_weight
),

group_violations as (

    select
        strategy_id,
        factor_group_id,
        'GROUP_FEATURE_WEIGHT_MISMATCH' as validation_type,
        group_weight as expected_weight,
        feature_weight_sum as actual_weight

    from group_validation

    where abs(group_weight - feature_weight_sum) >= 0.000001
),

strategy_weight_validation as (

    select
        strategy_id,
        sum(group_weight) as total_group_weight

    from {{ source('analytics', 'strategy_factor_groups') }}

    where enabled = true

    group by strategy_id
),

strategy_violations as (

    select
        strategy_id,
        null::varchar(50) as factor_group_id,
        'GROUP_WEIGHT_TOTAL_INVALID' as validation_type,
        1.000000::numeric as expected_weight,
        total_group_weight as actual_weight

    from strategy_weight_validation

    where abs(total_group_weight - 1.000000) >= 0.000001
)

select * from group_violations

union all

select * from strategy_violations
