{{ config(materialized='table') }}

select
    scv.configuration_id,
    scv.strategy_id,
    scv.configuration_version,
    scv.status as configuration_status,
    scv.strategy_name,

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

from {{ source('analytics', 'strategy_config_version_factor') }} sf

join {{ source('analytics', 'strategy_config_version_factor_group') }} fg
    on sf.configuration_id = fg.configuration_id
   and sf.factor_group_id = fg.factor_group_id

join {{ source('analytics', 'strategy_config_version') }} scv
    on sf.configuration_id = scv.configuration_id

join {{ source('metadata', 'feature_catalog') }} fc
    on sf.feature_id = fc.feature_id

where scv.status in ('VALIDATED', 'FROZEN')
