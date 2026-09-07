{{ config(materialized='table') }}

select
    sf.strategy_id,
    sc.strategy_name,
    fg.factor_group_id,
    fg.factor_group_name,
    fg.group_weight,
    sf.feature_id,
    fc.feature_name,
    fc.feature_type,
    fc.lookback_period,
    fc.parameter_1,
    fc.parameter_2,
    fc.annualization_factor,
    sf.feature_weight,
    sf.direction,
    sf.enabled as feature_enabled,
    fg.enabled as factor_group_enabled,
    fc.enabled as feature_catalog_enabled

from {{ source('analytics', 'strategy_factors') }} sf

join {{ source('analytics', 'strategy_factor_groups') }} fg
    on sf.strategy_id = fg.strategy_id
   and sf.factor_group_id = fg.factor_group_id

join {{ source('analytics', 'strategy_config') }} sc
    on sf.strategy_id = sc.strategy_id

join {{ source('metadata', 'feature_catalog') }} fc
    on sf.feature_id = fc.feature_id

where sc.status in ('ACTIVE', 'FROZEN')
