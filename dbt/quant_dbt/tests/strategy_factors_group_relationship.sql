select
    sf.strategy_id,
    sf.factor_group_id
from {{ source('analytics', 'strategy_factors') }} sf
left join {{ source('analytics', 'strategy_factor_groups') }} fg
    on sf.strategy_id = fg.strategy_id
   and sf.factor_group_id = fg.factor_group_id
where fg.strategy_id is null
