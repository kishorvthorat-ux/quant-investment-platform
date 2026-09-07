select
    r.trade_date,
    r.portfolio_daily_return,
    coalesce(t.portfolio_turnover, 0) as portfolio_turnover,

    coalesce(t.portfolio_turnover, 0) * 0.0020
        as transaction_cost,

    r.portfolio_daily_return
        - coalesce(t.portfolio_turnover, 0) * 0.0020
        as portfolio_net_return

from {{ ref('portfolio_daily_returns_monthly') }} r

left join {{ ref('portfolio_turnover_monthly') }} t
    on r.trade_date = t.trade_date
