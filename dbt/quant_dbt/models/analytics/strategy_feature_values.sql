{{ config(materialized='table') }}

with configured_features as (

    select
        strategy_id,
        factor_group_id,
        feature_id,
        feature_weight,
        direction
    from {{ ref('strategy_feature_configuration') }}
    where feature_enabled = true
      and factor_group_enabled = true
      and feature_catalog_enabled = true

),

feature_values as (

    select
        qf.trade_date,
        qf.security_id,
        qf.symbol,
        qf.exchange,

        cf.strategy_id,
        cf.factor_group_id,
        cf.feature_id,
        cf.feature_weight,
        cf.direction,

        case cf.feature_id
            when 'RETURN_20D' then qf.return_20d
            when 'RETURN_60D' then qf.return_60d
            when 'RETURN_252D' then qf.return_252d

            when 'PRICE_VS_MA_20D' then qf.price_vs_ma20
            when 'PRICE_VS_MA_60D' then qf.price_vs_ma60
            when 'PRICE_VS_MA_252D' then qf.price_vs_ma252

            when 'VOLATILITY_20D' then qf.volatility_20d
            when 'VOLATILITY_60D' then qf.volatility_60d
            when 'VOLATILITY_252D' then qf.volatility_252d

            when 'DRAWDOWN_252D' then qf.drawdown_252d

            else null
        end as feature_value

    from {{ ref('quant_features') }} qf

    cross join configured_features cf

)

select *
from feature_values
where feature_value is not null
