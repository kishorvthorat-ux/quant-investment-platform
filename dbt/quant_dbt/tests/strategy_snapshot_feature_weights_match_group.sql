select
    fg.configuration_id,
    fg.factor_group_id,
    fg.group_weight,
    coalesce(
        sum(sf.feature_weight) filter (where sf.enabled = true),
        0
    ) as feature_weight_sum
from {{ source('analytics', 'strategy_config_version_factor_group') }} fg
left join {{ source('analytics', 'strategy_config_version_factor') }} sf
    on fg.configuration_id = sf.configuration_id
   and fg.factor_group_id = sf.factor_group_id
where fg.enabled = true
group by
    fg.configuration_id,
    fg.factor_group_id,
    fg.group_weight
having abs(
    fg.group_weight
    - coalesce(
        sum(sf.feature_weight) filter (where sf.enabled = true),
        0
    )
) >= 0.000001
