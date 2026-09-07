with position_returns as (

    select
        p.position_date as trade_date,
        p.security_id,
        p.target_weight,
        r.daily_return

    from {{ ref('portfolio_positions_monthly') }} p

    inner join {{ ref('daily_returns') }} r
        on p.position_date = r.trade_date
       and p.security_id = r.security_id

)

select
    trade_date,
    sum(target_weight * daily_return) as portfolio_daily_return

from position_returns

group by trade_date
order by trade_date
