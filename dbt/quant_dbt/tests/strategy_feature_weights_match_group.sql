select
    configuration_id,
    strategy_id,
    factor_group_id,
    group_weight,
    sum(feature_weight) as feature_weight_sum
from {{ ref('strategy_feature_configuration') }}
where feature_enabled = true
  and factor_group_enabled = true
  and feature_catalog_enabled = true
group by
    configuration_id,
    strategy_id,
    factor_group_id,
    group_weight
having abs(group_weight - sum(feature_weight)) >= 0.000001
