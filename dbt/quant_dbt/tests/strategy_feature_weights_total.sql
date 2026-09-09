select
    configuration_id,
    strategy_id,
    sum(feature_weight) as total_feature_weight
from {{ ref('strategy_feature_configuration') }}
where feature_enabled = true
  and factor_group_enabled = true
  and feature_catalog_enabled = true
group by
    configuration_id,
    strategy_id
having abs(sum(feature_weight) - 1.000000) >= 0.000001
