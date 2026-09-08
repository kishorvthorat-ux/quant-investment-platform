select
    configuration_id,
    sum(feature_weight) as total_feature_weight
from {{ source('analytics', 'strategy_config_version_factor') }}
where enabled = true
group by configuration_id
having abs(sum(feature_weight) - 1.000000) >= 0.000001
