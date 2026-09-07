with daily as (

    select
        trade_date,
        portfolio_net_return,
        ln(1 + portfolio_net_return) as log_return
    from {{ ref('portfolio_net_returns_weekly') }}
    where portfolio_net_return is not null
      and portfolio_net_return > -1

),

cumulative as (

    select
        trade_date,
        portfolio_net_return,
        log_return,
        exp(
            sum(log_return)
            over (
                order by trade_date
                rows between unbounded preceding and current row
            )
        ) as cumulative_growth
    from daily

),

drawdown as (

    select
        trade_date,
        portfolio_net_return,
        log_return,
        cumulative_growth,
        cumulative_growth
        /
        max(cumulative_growth)
        over (
            order by trade_date
            rows between unbounded preceding and current row
        ) - 1 as drawdown
    from cumulative

),

summary as (

    select
        min(trade_date) as start_date,
        max(trade_date) as end_date,
        count(*) as trading_days,

        exp(sum(log_return)) - 1 as net_return,

        avg(portfolio_net_return) as avg_daily_return,

        stddev_samp(portfolio_net_return) as daily_volatility,

        min(drawdown) as max_drawdown,

        avg(
            case
                when portfolio_net_return > 0 then 1.0
                else 0.0
            end
        ) as win_rate,

        max(portfolio_net_return) as best_day,

        min(portfolio_net_return) as worst_day

    from drawdown
),

turnover as (

    select
        sum(portfolio_turnover) as total_turnover,
        sum(transaction_cost) as transaction_cost
    from {{ ref('portfolio_net_returns_weekly') }}

)

select

    s.start_date,
    s.end_date,
    s.trading_days,

    round(
        (s.net_return * 100)::numeric,
        2
    ) as net_return_pct,

    round(
        (
            power(
                1 + s.net_return,
                252.0 / s.trading_days
            ) - 1
        ) * 100
        ::numeric,
        2
    ) as net_cagr_pct,

    round(
        (
            s.daily_volatility
            * sqrt(252)
            * 100
        )::numeric,
        2
    ) as net_volatility_pct,

    round(
        (
            s.avg_daily_return
            / nullif(s.daily_volatility, 0)
            * sqrt(252)
        )::numeric,
        2
    ) as net_sharpe,

    round(
        (s.max_drawdown * 100)::numeric,
        2
    ) as net_max_drawdown_pct,

    round(
        (s.win_rate * 100)::numeric,
        2
    ) as net_win_rate_pct,

    round(
        (s.best_day * 100)::numeric,
        2
    ) as best_day_pct,

    round(
        (s.worst_day * 100)::numeric,
        2
    ) as worst_day_pct,

    round(
        t.total_turnover::numeric,
        2
    ) as total_turnover,

    round(
        (
            t.total_turnover
            / (s.trading_days / 252.0)
            * 100
        )::numeric,
        2
    ) as annualized_turnover_pct,

    round(
        (t.transaction_cost * 100)::numeric,
        2
    ) as transaction_cost_pct

from summary s
cross join turnover t
