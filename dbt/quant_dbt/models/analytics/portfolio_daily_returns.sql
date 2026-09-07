with positions as (
    select
        position_date,
        security_id,
        symbol,
        target_weight
    from {{ ref('portfolio_positions') }}
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
        p.target_weight,
        r.daily_return,
        p.target_weight * r.daily_return as weighted_return
    from positions p
    inner join returns r
        on p.position_date = r.trade_date
        and p.security_id = r.security_id
)

select
    trade_date,
    sum(weighted_return) as portfolio_daily_return
from portfolio_returns
group by trade_date
order by trade_date

