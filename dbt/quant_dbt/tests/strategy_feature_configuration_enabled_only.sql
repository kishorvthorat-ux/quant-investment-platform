select
    strategy_id,
    factor_group_id,
    feature_id
from {{ ref('strategy_feature_configuration') }}
where feature_enabled = false
   or factor_group_enabled = false
   or feature_catalog_enabled = false
