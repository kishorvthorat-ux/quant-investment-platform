select
    configuration_id,
    sum(group_weight) as total_group_weight
from {{ source('analytics', 'strategy_config_version_factor_group') }}
where enabled = true
group by configuration_id
having abs(sum(group_weight) - 1.000000) >= 0.000001
