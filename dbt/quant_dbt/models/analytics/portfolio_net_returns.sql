with gross_returns as (
    select
        trade_date,
        portfolio_daily_return
    from {{ ref('portfolio_daily_returns') }}
),

turnover as (
    select
        trade_date,
        portfolio_turnover
    from {{ ref('portfolio_turnover') }}
),

combined as (
    select
        g.trade_date,
        g.portfolio_daily_return,
        coalesce(t.portfolio_turnover, 0) as portfolio_turnover,

        coalesce(t.portfolio_turnover, 0) * 0.0020
            as transaction_cost

    from gross_returns g
    left join turnover t
        on g.trade_date = t.trade_date
)

select
    trade_date,
    portfolio_daily_return,
    portfolio_turnover,
    transaction_cost,

    portfolio_daily_return - transaction_cost
        as portfolio_net_return

from combined
order by trade_date
