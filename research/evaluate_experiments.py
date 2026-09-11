from __future__ import annotations

import duckdb
import pandas as pd
import numpy as np
from datetime import datetime, UTC


DB_PATH = "duckdb/analytics.duckdb"
DEFAULT_COST = 0.002


def get_connection():
    return duckdb.connect(DB_PATH)


def latest_batch(con):
    return con.execute("""
        select max(split_part(experiment_id, '_', 1)) as batch_id
        from analytics.main.experiment_runs
        where experiment_id like '%_%'
    """).fetchone()[0]


def create_output_tables(con):
    con.execute("""
        create table if not exists analytics.main.experiment_evaluations (
            experiment_id varchar,
            experiment_type varchar,
            experiment_name varchar,
            base_configuration_id bigint,
            status varchar,
            start_date date,
            end_date date,
            trading_periods integer,
            gross_return_pct double,
            gross_cagr_pct double,
            net_return_pct double,
            net_cagr_pct double,
            net_sharpe double,
            net_max_drawdown_pct double,
            net_win_rate_pct double,
            turnover_pct double,
            transaction_cost_pct double,
            delta_cagr_pct double,
            delta_sharpe double,
            evaluated_at timestamp
        )
    """)

    con.execute("""
        create table if not exists analytics.main.experiment_yearly_results (
            experiment_id varchar,
            year integer,
            gross_return_pct double,
            net_return_pct double,
            turnover_pct double,
            transaction_cost_pct double,
            evaluated_at timestamp,
            primary key (experiment_id, year)
        )
    """)


def build_weekly_returns(con, experiment_ids):
    ids = ",".join("'" + x.replace("'", "''") + "'" for x in experiment_ids)

    sql = f"""
        with holdings as (
            select
                experiment_id,
                trade_date,
                symbol,
                target_weight
            from analytics.main.experiment_portfolios
            where experiment_id in ({ids})
        ),

        prices as (
            select
                symbol,
                trade_date,
                close,
                lead(close) over (
                    partition by symbol
                    order by trade_date
                ) as next_close,
                lead(trade_date) over (
                    partition by symbol
                    order by trade_date
                ) as next_date
            from analytics.main.market_prices
        ),

        position_returns as (
            select
                h.experiment_id,
                h.trade_date,
                h.symbol,
                h.target_weight,
                p.close,
                p.next_close,
                p.next_date,
                case
                    when p.close is not null
                     and p.next_close is not null
                     and p.close <> 0
                    then p.next_close / p.close - 1
                    else null
                end as asset_return
            from holdings h
            left join prices p
                on h.symbol = p.symbol
               and h.trade_date = p.trade_date
        )

        select
            experiment_id,
            trade_date,
            sum(target_weight * asset_return) as gross_return
        from position_returns
        where asset_return is not null
        group by experiment_id, trade_date
        order by experiment_id, trade_date
    """

    return con.execute(sql).df()


def calculate_turnover(con, experiment_ids):
    ids = ",".join("'" + x.replace("'", "''") + "'" for x in experiment_ids)

    sql = f"""
        with holdings as (
            select
                experiment_id,
                trade_date,
                symbol,
                target_weight
            from analytics.main.experiment_portfolios
            where experiment_id in ({ids})
        ),

        dates as (
            select distinct
                experiment_id,
                trade_date
            from holdings
        ),

        symbols as (
            select distinct
                experiment_id,
                symbol
            from holdings
        ),

        grid as (
            select
                d.experiment_id,
                d.trade_date,
                s.symbol
            from dates d
            join symbols s
              on d.experiment_id = s.experiment_id
        ),

        current_weights as (
            select
                g.experiment_id,
                g.trade_date,
                g.symbol,
                coalesce(h.target_weight, 0.0) as current_weight
            from grid g
            left join holdings h
              on g.experiment_id = h.experiment_id
             and g.trade_date = h.trade_date
             and g.symbol = h.symbol
        ),

        previous_weights as (
            select
                experiment_id,
                trade_date,
                symbol,
                current_weight,
                lag(current_weight) over (
                    partition by experiment_id, symbol
                    order by trade_date
                ) as previous_weight
            from current_weights
        )

        select
            experiment_id,
            trade_date,
            sum(
                abs(
                    current_weight
                    - coalesce(previous_weight, 0.0)
                )
            ) as turnover
        from previous_weights
        group by experiment_id, trade_date
        order by experiment_id, trade_date
    """

    return con.execute(sql).df()


def calculate_metrics(df):
    if df.empty:
        return {
            "start_date": None,
            "end_date": None,
            "trading_periods": 0,
            "gross_return_pct": 0.0,
            "gross_cagr_pct": 0.0,
            "net_return_pct": 0.0,
            "net_cagr_pct": 0.0,
            "net_sharpe": 0.0,
            "net_max_drawdown_pct": 0.0,
            "net_win_rate_pct": 0.0,
            "turnover_pct": 0.0,
            "transaction_cost_pct": 0.0,
        }

    df = df.sort_values("trade_date").copy()

    gross = df["gross_return"].fillna(0.0)
    net = df["net_return"].fillna(0.0)

    gross_curve = (1.0 + gross).cumprod()
    net_curve = (1.0 + net).cumprod()

    gross_total = gross_curve.iloc[-1] - 1.0
    net_total = net_curve.iloc[-1] - 1.0

    start_date = pd.Timestamp(df["trade_date"].min())
    end_date = pd.Timestamp(df["trade_date"].max())

    years = max(
        (end_date - start_date).days / 365.25,
        1 / 365.25,
    )

    gross_cagr = (1.0 + gross_total) ** (1.0 / years) - 1.0
    net_cagr = (1.0 + net_total) ** (1.0 / years) - 1.0

    volatility = net.std(ddof=1)

    if volatility and np.isfinite(volatility) and volatility > 0:
        sharpe = net.mean() / volatility * np.sqrt(len(net))
    else:
        sharpe = 0.0

    running_max = net_curve.cummax()
    drawdown = net_curve / running_max - 1.0
    max_drawdown = drawdown.min()

    win_rate = (net > 0).mean()

    turnover = df["turnover"].fillna(0.0).sum()
    transaction_cost = df["transaction_cost"].fillna(0.0).sum()

    return {
        "start_date": start_date.date(),
        "end_date": end_date.date(),
        "trading_periods": len(df),
        "gross_return_pct": gross_total * 100,
        "gross_cagr_pct": gross_cagr * 100,
        "net_return_pct": net_total * 100,
        "net_cagr_pct": net_cagr * 100,
        "net_sharpe": sharpe,
        "net_max_drawdown_pct": max_drawdown * 100,
        "net_win_rate_pct": win_rate * 100,
        "turnover_pct": turnover * 100,
        "transaction_cost_pct": transaction_cost * 100,
    }


def yearly_results(df):
    if df.empty:
        return pd.DataFrame()

    rows = []

    temp = df.copy()
    temp["year"] = pd.to_datetime(temp["trade_date"]).dt.year

    for year, group in temp.groupby("year"):
        gross = group["gross_return"].fillna(0.0)
        net = group["net_return"].fillna(0.0)

        gross_return = ((1.0 + gross).prod() - 1.0) * 100
        net_return = ((1.0 + net).prod() - 1.0) * 100
        turnover = group["turnover"].fillna(0.0).sum() * 100
        cost = group["transaction_cost"].fillna(0.0).sum() * 100

        rows.append({
            "year": int(year),
            "gross_return_pct": gross_return,
            "net_return_pct": net_return,
            "turnover_pct": turnover,
            "transaction_cost_pct": cost,
        })

    return pd.DataFrame(rows)


def main():
    print("Selecting latest R&D experiment batch...")

    con = get_connection()

    batch_id = latest_batch(con)

    if not batch_id:
        raise RuntimeError("No R&D experiment batches found.")

    print(f"Latest batch: {batch_id}")

    experiments = con.execute(f"""
        select
            experiment_id,
            experiment_type,
            experiment_name,
            status
        from analytics.main.experiment_runs
        where split_part(experiment_id, '_', 1) = '{batch_id}'
        order by experiment_id
    """).df()

    if experiments.empty:
        raise RuntimeError(f"No experiments found for batch {batch_id}")

    experiment_ids = experiments["experiment_id"].tolist()

    print(f"Experiments found: {len(experiment_ids)}")
    print("Building weekly experiment returns...")

    returns = build_weekly_returns(con, experiment_ids)

    if returns.empty:
        raise RuntimeError("No experiment portfolio returns were generated.")

    print("Calculating turnover and transaction costs...")

    turnover = calculate_turnover(con, experiment_ids)

    df = returns.merge(
        turnover,
        on=["experiment_id", "trade_date"],
        how="left",
    )

    df["turnover"] = df["turnover"].fillna(0.0)
    df["transaction_cost"] = df["turnover"] * DEFAULT_COST
    df["net_return"] = df["gross_return"] - df["transaction_cost"]

    print("Calculating performance...")

    evaluated_at = datetime.now(UTC)

    results = []

    for _, exp in experiments.iterrows():
        exp_id = exp["experiment_id"]

        exp_df = df[df["experiment_id"] == exp_id].copy()

        metrics = calculate_metrics(exp_df)

        results.append({
            "experiment_id": exp_id,
            "experiment_type": exp["experiment_type"],
            "experiment_name": exp["experiment_name"],
            "status": exp["status"],
            **metrics,
        })

    result_df = pd.DataFrame(results)

    baseline_rows = result_df[
        result_df["experiment_name"] == "FACTOR_ABLATION_BASELINE_None"
    ]

    if len(baseline_rows) != 1:
        raise RuntimeError(
            "Expected exactly one FACTOR_ABLATION_BASELINE_None "
            f"experiment in the batch, found {len(baseline_rows)}."
        )

    baseline = baseline_rows.iloc[0]

    print(
        "Baseline selected explicitly: "
        f"{baseline['experiment_name']} "
        f"(experiment_id={baseline['experiment_id']})"
    )

    result_df["delta_cagr_pct"] = (
        result_df["net_cagr_pct"] - baseline["net_cagr_pct"]
    )

    result_df["delta_sharpe"] = (
        result_df["net_sharpe"] - baseline["net_sharpe"]
    )

    result_df["evaluated_at"] = evaluated_at

    print("Calculating yearly performance...")

    yearly_frames = []

    for exp_id in experiment_ids:
        exp_df = df[df["experiment_id"] == exp_id].copy()

        yearly = yearly_results(exp_df)

        if not yearly.empty:
            yearly.insert(0, "experiment_id", exp_id)
            yearly_frames.append(yearly)

    if yearly_frames:
        yearly_df = pd.concat(yearly_frames, ignore_index=True)
        yearly_df["evaluated_at"] = evaluated_at
    else:
        yearly_df = pd.DataFrame()

    print("Building baseline comparison...")

    con.execute("""
        delete from analytics.main.experiment_evaluations
        where experiment_id in (
            select experiment_id
            from analytics.main.experiment_runs
        )
    """)

    con.register("result_df", result_df)

    con.execute("""
        insert into analytics.main.experiment_evaluations (
            experiment_id,
            experiment_type,
            experiment_name,
            top_n,
            start_date,
            end_date,
            weeks,
            net_return_pct,
            net_cagr_pct,
            net_sharpe,
            net_max_drawdown_pct,
            net_win_rate_pct,
            gross_return_pct,
            transaction_cost_pct,
            turnover_pct,
            avg_weekly_turnover_pct,
            delta_cagr_pct,
            delta_sharpe,
            evaluated_at
        )
        select
            experiment_id,
            experiment_type,
            experiment_name,
            null as top_n,
            start_date,
            end_date,
            trading_periods as weeks,
            net_return_pct,
            net_cagr_pct,
            net_sharpe,
            net_max_drawdown_pct,
            net_win_rate_pct,
            gross_return_pct,
            transaction_cost_pct,
            turnover_pct,
            case when trading_periods > 0 then turnover_pct / trading_periods else 0 end as avg_weekly_turnover_pct,
            delta_cagr_pct,
            delta_sharpe,
            evaluated_at
        from result_df
    """)

    if not yearly_df.empty:
        con.register("yearly_df", yearly_df)

        con.execute("""
            delete from analytics.main.experiment_yearly_results
            where experiment_id in (
                select experiment_id
                from analytics.main.experiment_runs
            )
        """)

        con.execute("""
            insert into analytics.main.experiment_yearly_results (
                experiment_id,
                year,
                return_pct,
                weeks
            )
            select
                experiment_id,
                year,
                net_return_pct,
                1
            from yearly_df
        """)

    con.execute(f"""
        update analytics.main.experiment_runs
        set status = 'COMPLETED'
        where split_part(experiment_id, '_', 1) = '{batch_id}'
    """)

    print()
    print("=== R&D EXPERIMENT COMPARISON ===")
    print()

    print(
        result_df[
            [
                "experiment_type",
                "experiment_name",
                "net_return_pct",
                "net_cagr_pct",
                "net_sharpe",
                "net_max_drawdown_pct",
                "net_win_rate_pct",
                "turnover_pct",
                "transaction_cost_pct",
                "delta_cagr_pct",
                "delta_sharpe",
            ]
        ].to_string(
            index=False,
            formatters={
                "net_return_pct": "{:.2f}".format,
                "net_cagr_pct": "{:.2f}".format,
                "net_sharpe": "{:.2f}".format,
                "net_max_drawdown_pct": "{:.2f}".format,
                "net_win_rate_pct": "{:.2f}".format,
                "turnover_pct": "{:.2f}".format,
                "transaction_cost_pct": "{:.2f}".format,
                "delta_cagr_pct": "{:.2f}".format,
                "delta_sharpe": "{:.2f}".format,
            },
        )
    )

    print()
    print(f"Experiments evaluated: {len(result_df)}")
    print("R&D evaluation completed successfully.")

    con.close()


if __name__ == "__main__":
    main()
