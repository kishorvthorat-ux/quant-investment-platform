with positions as (

    select
        position_date,
        security_id,
        symbol,
        configuration_id,
        strategy_id,
        target_weight
    from {{ ref('portfolio_positions_v2') }}

),

returns as (

    select
        trade_date,
        security_id,
        symbol,
        daily_return
    from {{ ref('daily_returns') }}

),

portfolio_returns as (

    select
        p.position_date as trade_date,
        p.security_id,
        p.symbol,
        p.configuration_id,
        p.strategy_id,
        p.target_weight,
        r.daily_return,

        p.target_weight * r.daily_return
            as weighted_return

    from positions p

    inner join returns r
        on p.position_date = r.trade_date
        and p.security_id = r.security_id

)

select
    trade_date,
    configuration_id,
    strategy_id,
    sum(weighted_return) as portfolio_daily_return

from portfolio_returns

group by
    trade_date,
    configuration_id,
    strategy_id

order by
    trade_date,
    configuration_id
