with gross_returns as (

    select
        trade_date,
        configuration_id,
        strategy_id,
        portfolio_daily_return
    from {{ ref('portfolio_daily_returns_v2') }}

),

turnover as (

    select
        trade_date,
        configuration_id,
        strategy_id,
        portfolio_turnover
    from {{ ref('portfolio_turnover_v2') }}

),

configurations as (

    select
        configuration_id,
        transaction_cost_rate
    from {{ source('analytics', 'strategy_config_version') }}

),

combined as (

    select
        g.trade_date,
        g.configuration_id,
        g.strategy_id,
        g.portfolio_daily_return,
        coalesce(t.portfolio_turnover, 0) as portfolio_turnover,

        coalesce(t.portfolio_turnover, 0)
            * c.transaction_cost_rate
            as transaction_cost

    from gross_returns g

    left join turnover t
        on g.trade_date = t.trade_date
        and g.configuration_id = t.configuration_id
        and g.strategy_id = t.strategy_id

    join configurations c
        on g.configuration_id = c.configuration_id

)

select
    trade_date,
    configuration_id,
    strategy_id,
    portfolio_daily_return,
    portfolio_turnover,
    transaction_cost,

    portfolio_daily_return - transaction_cost
        as portfolio_net_return

from combined

order by
    trade_date,
    configuration_id
