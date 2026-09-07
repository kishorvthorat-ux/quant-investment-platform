with daily_returns as (
    select
        trade_date,
        portfolio_daily_return
    from {{ ref('portfolio_daily_returns') }}
),

performance as (
    select
        trade_date,
        portfolio_daily_return,

        exp(
            sum(
                ln(1 + portfolio_daily_return)
            ) over (
                order by trade_date
                rows between unbounded preceding and current row
            )
        ) as cumulative_growth

    from daily_returns
)

select
    trade_date,
    portfolio_daily_return,
    cumulative_growth,
    cumulative_growth - 1 as cumulative_return
from performance
order by trade_date
