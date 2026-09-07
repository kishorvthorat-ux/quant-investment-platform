with gross as (
    select
        min(trade_date) as start_date,
        max(trade_date) as end_date,
        count(*) as trading_days,
        avg(portfolio_daily_return) as avg_daily_return,
        stddev_samp(portfolio_daily_return) as daily_volatility,
        sum(case when portfolio_daily_return > 0 then 1 else 0 end) as winning_days,
        sum(case when portfolio_daily_return < 0 then 1 else 0 end) as losing_days,
        max(portfolio_daily_return) as best_day,
        min(portfolio_daily_return) as worst_day
    from {{ ref('portfolio_daily_returns') }}
),

gross_growth as (
    select
        trade_date,
        exp(
            sum(
                ln(1 + portfolio_daily_return)
            ) over (
                order by trade_date
                rows between unbounded preceding and current row
            )
        ) as growth
    from {{ ref('portfolio_daily_returns') }}
),

gross_drawdown as (
    select
        trade_date,
        growth,
        max(growth) over (
            order by trade_date
            rows between unbounded preceding and current row
        ) as running_peak
    from gross_growth
),

gross_metrics as (
    select
        g.start_date,
        g.end_date,
        g.trading_days,
        g.avg_daily_return,
        g.daily_volatility,
        g.winning_days,
        g.losing_days,
        g.best_day,
        g.worst_day,

        max(dd.growth) as final_growth,

        min(
            (dd.growth / dd.running_peak) - 1
        ) as max_drawdown

    from gross g
    cross join gross_drawdown dd
    group by
        g.start_date,
        g.end_date,
        g.trading_days,
        g.avg_daily_return,
        g.daily_volatility,
        g.winning_days,
        g.losing_days,
        g.best_day,
        g.worst_day
),

net as (
    select
        min(trade_date) as start_date,
        max(trade_date) as end_date,
        count(*) as trading_days,
        avg(portfolio_net_return) as avg_daily_return,
        stddev_samp(portfolio_net_return) as daily_volatility,
        sum(case when portfolio_net_return > 0 then 1 else 0 end) as winning_days,
        sum(case when portfolio_net_return < 0 then 1 else 0 end) as losing_days,
        max(portfolio_net_return) as best_day,
        min(portfolio_net_return) as worst_day
    from {{ ref('portfolio_net_returns') }}
),

net_growth as (
    select
        trade_date,
        exp(
            sum(
                ln(1 + portfolio_net_return)
            ) over (
                order by trade_date
                rows between unbounded preceding and current row
            )
        ) as growth
    from {{ ref('portfolio_net_returns') }}
),

net_drawdown as (
    select
        trade_date,
        growth,
        max(growth) over (
            order by trade_date
            rows between unbounded preceding and current row
        ) as running_peak
    from net_growth
),

net_metrics as (
    select
        n.start_date,
        n.end_date,
        n.trading_days,
        n.avg_daily_return,
        n.daily_volatility,
        n.winning_days,
        n.losing_days,
        n.best_day,
        n.worst_day,

        max(dd.growth) as final_growth,

        min(
            (dd.growth / dd.running_peak) - 1
        ) as max_drawdown

    from net n
    cross join net_drawdown dd
    group by
        n.start_date,
        n.end_date,
        n.trading_days,
        n.avg_daily_return,
        n.daily_volatility,
        n.winning_days,
        n.losing_days,
        n.best_day,
        n.worst_day
),

trading as (
    select
        sum(portfolio_turnover) as total_turnover,
        avg(portfolio_turnover) as avg_daily_turnover,
        sum(transaction_cost) as total_transaction_cost
    from {{ ref('portfolio_net_returns') }}
)

select
    -- Backtest period
    gross.start_date,
    gross.end_date,
    gross.trading_days,

    -- Gross performance
    gross.final_growth - 1 as gross_cumulative_return,

    power(
        gross.final_growth,
        365.25 /
        nullif(
            (gross.end_date - gross.start_date),
            0
        )
    ) - 1 as gross_cagr,

    gross.daily_volatility * sqrt(252) as gross_annualized_volatility,

    (
        gross.avg_daily_return * 252
    ) /
    nullif(
        gross.daily_volatility * sqrt(252),
        0
    ) as gross_sharpe,

    gross.max_drawdown as gross_max_drawdown,

    -- Net performance
    net.final_growth - 1 as net_cumulative_return,

    power(
        net.final_growth,
        365.25 /
        nullif(
            (net.end_date - net.start_date),
            0
        )
    ) - 1 as net_cagr,

    net.daily_volatility * sqrt(252) as net_annualized_volatility,

    (
        net.avg_daily_return * 252
    ) /
    nullif(
        net.daily_volatility * sqrt(252),
        0
    ) as net_sharpe,

    net.max_drawdown as net_max_drawdown,

    -- Trading statistics
    trading.total_turnover,
    trading.avg_daily_turnover,

    trading.avg_daily_turnover * 252
        as annualized_turnover,

    trading.total_transaction_cost,

    -- Hit rate
    gross.winning_days,
    gross.losing_days,

    gross.winning_days::numeric /
        nullif(
            gross.winning_days + gross.losing_days,
            0
        ) as gross_win_rate,

    net.winning_days::numeric /
        nullif(
            net.winning_days + net.losing_days,
            0
        ) as net_win_rate,

    -- Extremes
    gross.best_day as gross_best_day,
    gross.worst_day as gross_worst_day,
    net.best_day as net_best_day,
    net.worst_day as net_worst_day

from gross_metrics gross
cross join net_metrics net
cross join trading
