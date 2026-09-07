with gross_returns as (

    select
        trade_date,
        portfolio_daily_return
    from {{ ref('portfolio_daily_returns_v2') }}

),

net_returns as (

    select
        trade_date,
        portfolio_net_return,
        portfolio_turnover,
        transaction_cost
    from {{ ref('portfolio_net_returns_v2') }}

),

gross_growth as (

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

    from gross_returns

),

net_growth as (

    select
        trade_date,
        portfolio_net_return,
        portfolio_turnover,
        transaction_cost,

        exp(
            sum(
                ln(1 + portfolio_net_return)
            ) over (
                order by trade_date
                rows between unbounded preceding and current row
            )
        ) as cumulative_growth

    from net_returns

),

gross_stats as (

    select
        min(trade_date) as start_date,
        max(trade_date) as end_date,
        count(*) as trading_days,

        avg(portfolio_daily_return) as avg_daily_return,
        stddev_samp(portfolio_daily_return) as daily_volatility,

        max(cumulative_growth) as max_growth,

        (
            select cumulative_growth
            from gross_growth
            order by trade_date desc
            limit 1
        ) as final_growth

    from gross_growth

),

net_stats as (

    select
        min(trade_date) as start_date,
        max(trade_date) as end_date,
        count(*) as trading_days,

        avg(portfolio_net_return) as avg_daily_return,
        stddev_samp(portfolio_net_return) as daily_volatility,

        (
            select cumulative_growth
            from net_growth
            order by trade_date desc
            limit 1
        ) as final_growth,

        sum(portfolio_turnover) as total_turnover,

        avg(portfolio_turnover) as avg_daily_turnover,

        sum(transaction_cost) as total_transaction_cost

    from net_growth

),

gross_drawdown as (

    select
        trade_date,
        cumulative_growth,

        max(cumulative_growth) over (
            order by trade_date
            rows between unbounded preceding and current row
        ) as running_peak

    from gross_growth

),

net_drawdown as (

    select
        trade_date,
        cumulative_growth,

        max(cumulative_growth) over (
            order by trade_date
            rows between unbounded preceding and current row
        ) as running_peak

    from net_growth

),

gross_drawdown_stats as (

    select
        min(
            (cumulative_growth / running_peak) - 1
        ) as max_drawdown

    from gross_drawdown

),

net_drawdown_stats as (

    select
        min(
            (cumulative_growth / running_peak) - 1
        ) as max_drawdown

    from net_drawdown

),

gross_daily_stats as (

    select
        max(portfolio_daily_return) as best_day,
        min(portfolio_daily_return) as worst_day,

        100.0
        * sum(
            case
                when portfolio_daily_return > 0 then 1
                else 0
            end
        )
        / nullif(
            sum(
                case
                    when portfolio_daily_return != 0 then 1
                    else 0
                end
            ),
            0
        ) as win_rate

    from gross_returns

),

net_daily_stats as (

    select
        max(portfolio_net_return) as best_day,
        min(portfolio_net_return) as worst_day,

        100.0
        * sum(
            case
                when portfolio_net_return > 0 then 1
                else 0
            end
        )
        / nullif(
            sum(
                case
                    when portfolio_net_return != 0 then 1
                    else 0
                end
            ),
            0
        ) as win_rate

    from net_returns

)

select

    -- Period
    g.start_date,
    g.end_date,
    g.trading_days,

    -- Gross performance
    100.0 * (g.final_growth - 1)
        as gross_return_pct,

    100.0 * (
        power(
            g.final_growth,
            365.25
            / nullif(
                (g.end_date - g.start_date),
                0
            )
        ) - 1
    )
        as gross_cagr_pct,

    100.0
    * g.daily_volatility
    * sqrt(252)
        as gross_volatility_pct,

    (
        g.avg_daily_return * 252
        /
        nullif(
            g.daily_volatility * sqrt(252),
            0
        )
    )
        as gross_sharpe,

    100.0 * gd.max_drawdown
        as gross_max_drawdown_pct,

    -- Net performance
    100.0 * (n.final_growth - 1)
        as net_return_pct,

    100.0 * (
        power(
            n.final_growth,
            365.25
            / nullif(
                (n.end_date - n.start_date),
                0
            )
        ) - 1
    )
        as net_cagr_pct,

    100.0
    * n.daily_volatility
    * sqrt(252)
        as net_volatility_pct,

    (
        n.avg_daily_return * 252
        /
        nullif(
            n.daily_volatility * sqrt(252),
            0
        )
    )
        as net_sharpe,

    100.0 * nd.max_drawdown
        as net_max_drawdown_pct,

    -- Turnover
    n.total_turnover,

    100.0
    * n.avg_daily_turnover
    * 252
        as annualized_turnover_pct,

    100.0 * n.total_transaction_cost
        as transaction_cost_pct,

    -- Win rate
    ng.win_rate as net_win_rate_pct,

    -- Best / worst days
    100.0 * ng.best_day as best_day_pct,
    100.0 * ng.worst_day as worst_day_pct

from gross_stats g

cross join net_stats n

cross join gross_drawdown_stats gd

cross join net_drawdown_stats nd

cross join net_daily_stats ng
