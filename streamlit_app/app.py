import subprocess
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

from db import query_df, query_duckdb

def safe_int(value):
    if value is None or pd.isna(value):
        return None
    return int(value)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.run_experiment import (
    run_custom_experiment,
    DEFAULT_GROUP_WEIGHTS,
    DEFAULT_FACTOR_WEIGHTS,
    FACTOR_GROUPS,
)

st.set_page_config(
    page_title="Quant Investment Platform",
    page_icon="📈",
    layout="wide",
)

st.title("Quant Investment Platform")
st.caption("Personal quantitative investing dashboard")


tab_status, tab_signals, tab_performance, tab_rnd, tab_config = st.tabs(
    [
        "🏠 System Status",
        "📊 Signal Review",
        "📈 Strategy Performance",
        "🧪 R&D",
        "⚙️ Configuration Manager",
    ]
)

# ============================================================
# SYSTEM STATUS
# ============================================================

with tab_status:

    st.header("System Status")

    try:
        status = query_df(
            """
            SELECT
                COUNT(*) AS market_price_rows,
                MIN(trade_date) AS first_market_date,
                MAX(trade_date) AS latest_market_date,
                COUNT(DISTINCT symbol) AS symbols
            FROM raw.market_prices
            """
        )

        row = status.iloc[0]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Market Price Rows",
            f"{int(row['market_price_rows']):,}",
        )

        col2.metric(
            "Symbols",
            int(row["symbols"]),
        )

        col3.metric(
            "First Market Date",
            str(row["first_market_date"]),
        )

        col4.metric(
            "Latest Market Date",
            str(row["latest_market_date"]),
        )

        st.success("PostgreSQL connection: Healthy")

    except Exception as e:
        st.error(f"Unable to connect to PostgreSQL: {e}")


# ============================================================
# WEEKLY SIGNAL REVIEW
# ============================================================

with tab_signals:

    st.header("Weekly Signal Review")

    try:
        signal_dates = query_df(
            """
            SELECT DISTINCT signal_date
            FROM analytics.weekly_signals_v2
            ORDER BY signal_date DESC
            """
        )

        if signal_dates.empty:
            st.info("No weekly signals available.")

        else:
            selected_date = st.selectbox(
                "Signal Week",
                signal_dates["signal_date"].tolist(),
                format_func=lambda x: str(x),
            )

            strategies = query_df(
                """
                SELECT DISTINCT strategy_id
                FROM analytics.weekly_signals_v2
                WHERE signal_date = %(signal_date)s
                ORDER BY strategy_id
                """,
                params={"signal_date": selected_date},
            )

            selected_strategy = st.selectbox(
                "Strategy",
                strategies["strategy_id"].tolist(),
                key="signal_strategy",
            )

            configurations = query_df(
                """
                SELECT DISTINCT configuration_id
                FROM analytics.weekly_signals_v2
                WHERE signal_date = %(signal_date)s
                  AND strategy_id = %(strategy_id)s
                ORDER BY configuration_id
                """,
                params={
                    "signal_date": selected_date,
                    "strategy_id": selected_strategy,
                },
            )

            selected_config = st.selectbox(
                "Configuration",
                configurations["configuration_id"].tolist(),
                format_func=lambda x: f"Top {int(x)}",
                key="signal_configuration",
            )

            signals = query_df(
                """
                SELECT
                    signal_date,
                    execution_date,
                    symbol,
                    configuration_id,
                    strategy_id,
                    previous_rank,
                    current_rank,
                    previous_weight,
                    current_weight,
                    current_composite_score,
                    signal
                FROM analytics.weekly_signals_v2
                WHERE signal_date = %(signal_date)s
                  AND strategy_id = %(strategy_id)s
                  AND configuration_id = %(configuration_id)s
                ORDER BY
                    CASE signal
                        WHEN 'BUY' THEN 1
                        WHEN 'SELL' THEN 2
                        WHEN 'HOLD' THEN 3
                        ELSE 4
                    END,
                    current_rank NULLS LAST,
                    symbol
                """,
                params={
                    "signal_date": selected_date,
                    "strategy_id": selected_strategy,
                    "configuration_id": selected_config,
                },
            )

            if signals.empty:
                st.info(
                    "No signals available for the selected configuration."
                )

            else:
                execution_date = signals["execution_date"].iloc[0]

                st.caption(
                    f"Signal date: {selected_date}  |  "
                    f"Execution date: {execution_date}"
                )

                buy_count = int(
                    (signals["signal"] == "BUY").sum()
                )
                hold_count = int(
                    (signals["signal"] == "HOLD").sum()
                )
                sell_count = int(
                    (signals["signal"] == "SELL").sum()
                )

                col1, col2, col3 = st.columns(3)

                col1.metric("BUY", buy_count)
                col2.metric("HOLD", hold_count)
                col3.metric("SELL", sell_count)

                display = signals[
                    [
                        "symbol",
                        "previous_rank",
                        "current_rank",
                        "previous_weight",
                        "current_weight",
                        "current_composite_score",
                        "signal",
                    ]
                ].copy()

                display = display.rename(
                    columns={
                        "symbol": "Symbol",
                        "previous_rank": "Previous Rank",
                        "current_rank": "Current Rank",
                        "previous_weight": "Previous Weight",
                        "current_weight": "Target Weight",
                        "current_composite_score": "Score",
                        "signal": "Signal",
                    }
                )

                display["Previous Weight"] = (
                    display["Previous Weight"].fillna(0) * 100
                ).round(2).astype(str) + "%"

                display["Target Weight"] = (
                    display["Target Weight"].fillna(0) * 100
                ).round(2).astype(str) + "%"

                display["Score"] = display["Score"].round(4)

                st.dataframe(
                    display,
                    use_container_width=True,
                    hide_index=True,
                )

    except Exception as e:
        st.error(f"Unable to load weekly signals: {e}")


# ============================================================
# STRATEGY PERFORMANCE
# ============================================================

with tab_performance:

    st.header("Strategy Performance")

    try:
        performance = query_df(
            """
            SELECT
                configuration_id,
                strategy_id,
                start_date,
                end_date,
                trading_days,
                gross_return_pct,
                gross_cagr_pct,
                gross_volatility_pct,
                gross_sharpe,
                gross_max_drawdown_pct,
                net_return_pct,
                net_cagr_pct,
                net_volatility_pct,
                net_sharpe,
                net_max_drawdown_pct,
                annualized_turnover_pct,
                transaction_cost_pct,
                net_win_rate_pct,
                best_day_pct,
                worst_day_pct
            FROM analytics.portfolio_performance_metrics_v2
            ORDER BY strategy_id, configuration_id
            """
        )

        if performance.empty:
            st.info("No strategy performance data available.")

        else:
            strategies = (
                performance["strategy_id"]
                .dropna()
                .unique()
                .tolist()
            )

            selected_perf_strategy = st.selectbox(
                "Strategy",
                strategies,
                key="performance_strategy",
            )

            perf = performance[
                performance["strategy_id"] == selected_perf_strategy
            ].copy()

            perf["Configuration"] = (
                "Top "
                + perf["configuration_id"].astype(int).astype(str)
            )

            st.subheader("Net Performance")

            for _, row in perf.iterrows():

                st.markdown(f"**{row['Configuration']}**")

                col1, col2, col3, col4, col5 = st.columns(5)

                col1.metric(
                    "Net Return",
                    f"{row['net_return_pct']:.2f}%",
                )

                col2.metric(
                    "Net CAGR",
                    f"{row['net_cagr_pct']:.2f}%",
                )

                col3.metric(
                    "Net Sharpe",
                    f"{row['net_sharpe']:.2f}",
                )

                col4.metric(
                    "Max Drawdown",
                    f"{row['net_max_drawdown_pct']:.2f}%",
                )

                col5.metric(
                    "Win Rate",
                    f"{row['net_win_rate_pct']:.2f}%",
                )

            st.subheader("Configuration Comparison")

            comparison = perf[
                [
                    "Configuration",
                    "start_date",
                    "end_date",
                    "trading_days",
                    "net_return_pct",
                    "net_cagr_pct",
                    "net_sharpe",
                    "net_volatility_pct",
                    "net_max_drawdown_pct",
                    "net_win_rate_pct",
                    "annualized_turnover_pct",
                    "transaction_cost_pct",
                    "best_day_pct",
                    "worst_day_pct",
                ]
            ].copy()

            comparison = comparison.rename(
                columns={
                    "start_date": "Start",
                    "end_date": "End",
                    "trading_days": "Trading Days",
                    "net_return_pct": "Net Return %",
                    "net_cagr_pct": "Net CAGR %",
                    "net_sharpe": "Net Sharpe",
                    "net_volatility_pct": "Net Volatility %",
                    "net_max_drawdown_pct": "Max Drawdown %",
                    "net_win_rate_pct": "Win Rate %",
                    "annualized_turnover_pct": "Annualized Turnover %",
                    "transaction_cost_pct": "Transaction Cost %",
                    "best_day_pct": "Best Day %",
                    "worst_day_pct": "Worst Day %",
                }
            )

            numeric_columns = [
                "Net Return %",
                "Net CAGR %",
                "Net Sharpe",
                "Net Volatility %",
                "Max Drawdown %",
                "Win Rate %",
                "Annualized Turnover %",
                "Transaction Cost %",
                "Best Day %",
                "Worst Day %",
            ]

            comparison[numeric_columns] = (
                comparison[numeric_columns].round(2)
            )

            st.dataframe(
                comparison,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Gross vs Net")

            gross_net = perf[
                [
                    "Configuration",
                    "gross_return_pct",
                    "net_return_pct",
                    "gross_cagr_pct",
                    "net_cagr_pct",
                    "gross_sharpe",
                    "net_sharpe",
                    "gross_max_drawdown_pct",
                    "net_max_drawdown_pct",
                ]
            ].copy()

            gross_net = gross_net.rename(
                columns={
                    "gross_return_pct": "Gross Return %",
                    "net_return_pct": "Net Return %",
                    "gross_cagr_pct": "Gross CAGR %",
                    "net_cagr_pct": "Net CAGR %",
                    "gross_sharpe": "Gross Sharpe",
                    "net_sharpe": "Net Sharpe",
                    "gross_max_drawdown_pct": "Gross Max Drawdown %",
                    "net_max_drawdown_pct": "Net Max Drawdown %",
                }
            )

            gross_net.iloc[:, 1:] = (
                gross_net.iloc[:, 1:].round(2)
            )

            st.dataframe(
                gross_net,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Performance is based on the existing V2 portfolio "
                "performance models and includes the configured "
                "transaction-cost assumptions."
            )

    except Exception as e:
        st.error(f"Unable to load strategy performance: {e}")

# ============================================================
# R&D / EXPERIMENT REVIEW
# ============================================================

with tab_rnd:

    st.header("R&D Experiment Review")

    # ========================================================
    # CUSTOM R&D EXPERIMENT RUNNER
    # ========================================================

    st.subheader("🧪 Custom R&D Experiment")

    st.caption(
        "Adjust research parameters and run a new experiment. "
        "These settings affect R&D only and never modify the "
        "production strategy configuration."
    )

    with st.expander("⚖️ Factor Group Weights", expanded=True):

        group_cols = st.columns(4)

        group_weights = {}

        group_labels = {
            "MOMENTUM": "Momentum",
            "TREND": "Trend",
            "RISK": "Risk",
            "DRAWDOWN": "Drawdown",
        }

        for col, group in zip(group_cols, DEFAULT_GROUP_WEIGHTS):

            group_weights[group] = col.number_input(
                group_labels[group],
                min_value=0.0,
                max_value=1.0,
                value=float(DEFAULT_GROUP_WEIGHTS[group]),
                step=0.01,
                format="%.2f",
                key=f"rnd_group_{group}",
            )

        group_total = sum(group_weights.values())

        if group_total <= 0:
            st.error(
                "At least one factor group must have a weight greater than zero."
            )

        st.caption(
            f"Group weight total: {group_total:.2f} "
            "(the research engine normalizes weights before scoring)"
        )

    with st.expander("🔬 Individual Factor Weights", expanded=False):

        factor_weights = {}

        factor_labels = {
            "return_20d": "Return 20D",
            "return_60d": "Return 60D",
            "return_252d": "Return 252D",
            "price_vs_ma_20d": "Price vs MA 20D",
            "price_vs_ma_60d": "Price vs MA 60D",
            "price_vs_ma_252d": "Price vs MA 252D",
            "volatility_20d": "Volatility 20D",
            "volatility_60d": "Volatility 60D",
            "volatility_252d": "Volatility 252D",
            "drawdown_252d": "Drawdown 252D",
        }

        for group in FACTOR_GROUPS:

            st.markdown(f"**{group_labels[group]}**")

            factor_cols = st.columns(len(FACTOR_GROUPS[group]))

            for col, factor in zip(
                factor_cols,
                FACTOR_GROUPS[group],
            ):

                enabled = col.checkbox(
                    "Enabled",
                    value=True,
                    key=f"rnd_enabled_{factor}",
                )

                if enabled:
                    factor_weights[factor] = col.number_input(
                        factor_labels[factor],
                        min_value=0.0,
                        max_value=1.0,
                        value=float(DEFAULT_FACTOR_WEIGHTS[factor]),
                        step=0.01,
                        format="%.2f",
                        key=f"rnd_factor_{factor}",
                    )
                else:
                    factor_weights[factor] = 0.0

    with st.expander("⚙️ Backtest Settings", expanded=True):

        settings_col1, settings_col2 = st.columns(2)

        top_n = settings_col1.number_input(
            "Top N positions",
            min_value=1,
            max_value=20,
            value=2,
            step=1,
            key="rnd_top_n",
        )

        transaction_cost_pct = settings_col2.number_input(
            "Transaction cost (%)",
            min_value=0.0,
            max_value=5.0,
            value=0.20,
            step=0.05,
            format="%.2f",
            key="rnd_transaction_cost",
        )

        transaction_cost_rate = transaction_cost_pct / 100.0

    st.divider()

    run_rnd = st.button(
        "▶ Run R&D Experiment",
        type="primary",
        use_container_width=True,
        key="run_custom_rnd",
    )

    if run_rnd:

        if group_total <= 0:

            st.error(
                "Cannot run experiment: all factor-group weights are zero."
            )

        elif not any(
            weight > 0
            for weight in factor_weights.values()
        ):

            st.error(
                "Cannot run experiment: at least one factor must be enabled."
            )

        else:

            try:

                with st.spinner(
                    "Running R&D experiment and evaluating results..."
                ):

                    experiment_id = run_custom_experiment(
                        group_weights=group_weights,
                        factor_weights=factor_weights,
                        top_n=int(top_n),
                        transaction_cost_rate=transaction_cost_rate,
                    )

                    evaluation = subprocess.run(
                        [
                            sys.executable,
                            str(
                                PROJECT_ROOT
                                / "research"
                                / "evaluate_experiments.py"
                            ),
                        ],
                        cwd=str(PROJECT_ROOT),
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                st.success(
                    f"R&D experiment completed: {experiment_id}"
                )

                st.session_state["rnd_last_experiment"] = experiment_id
                st.session_state["rnd_evaluation_output"] = evaluation.stdout

                st.rerun()

            except subprocess.CalledProcessError as e:

                st.error(
                    "R&D experiment was created, but evaluation failed."
                )

                st.code(
                    e.stdout + "\n" + e.stderr,
                    language="text",
                )

            except Exception as e:

                st.error(
                    f"Unable to run R&D experiment: {e}"
                )

    st.caption(
        "Research-only experiment analysis. "
        "Production strategy configurations are not modified from this tab."
    )

    # ========================================================
    # R&D REVIEW
    # ========================================================

    try:

        # ----------------------------------------------------
        # Latest experiment batch
        # ----------------------------------------------------

        batch_info = query_duckdb(
            """
            SELECT
                split_part(experiment_id, '_', 1) AS batch_id,
                COUNT(*) AS experiment_count,
                COUNT(*) FILTER (
                    WHERE status = 'COMPLETED'
                ) AS completed_count,
                COUNT(*) FILTER (
                    WHERE status <> 'COMPLETED'
                ) AS non_completed_count,
                MIN(created_at) AS batch_created_at
            FROM analytics.main.experiment_runs
            WHERE split_part(experiment_id, '_', 1) = (
                SELECT MAX(split_part(experiment_id, '_', 1))
                FROM analytics.main.experiment_runs
            )
            GROUP BY split_part(experiment_id, '_', 1)
            """
        )

        if batch_info.empty:

            st.info("No R&D experiments available.")

        else:

            batch = batch_info.iloc[0]
            batch_id = str(batch["batch_id"])

            st.subheader("📦 Latest R&D Batch")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Batch",
                batch_id,
            )

            col2.metric(
                "Experiments",
                int(batch["experiment_count"]),
            )

            col3.metric(
                "Completed",
                int(batch["completed_count"]),
            )

            col4.metric(
                "Non-completed",
                int(batch["non_completed_count"]),
            )

            st.caption(
                f"Batch created: {batch['batch_created_at']}"
            )

            # ------------------------------------------------
            # Evaluation results
            # ------------------------------------------------

            evaluations = query_duckdb(
                """
                SELECT
                    e.experiment_id,
                    e.experiment_type,
                    e.experiment_name,
                    e.top_n,
                    r.transaction_cost_rate,
                    r.status,
                    e.start_date,
                    e.end_date,
                    e.weeks,
                    e.net_return_pct,
                    e.net_cagr_pct,
                    e.net_sharpe,
                    e.net_max_drawdown_pct,
                    e.net_win_rate_pct,
                    e.gross_return_pct,
                    e.transaction_cost_pct,
                    e.turnover_pct,
                    e.avg_weekly_turnover_pct,
                    e.delta_cagr_pct,
                    e.delta_sharpe,
                    e.evaluated_at
                FROM analytics.main.experiment_evaluations e
                JOIN analytics.main.experiment_runs r
                  ON e.experiment_id = r.experiment_id
                WHERE split_part(e.experiment_id, '_', 1) = ?
                ORDER BY
                    CASE
                        WHEN e.experiment_name =
                            'FACTOR_ABLATION_BASELINE_None'
                        THEN 0
                        ELSE 1
                    END,
                    e.net_cagr_pct DESC
                """,
                [batch_id],
            )

            if evaluations.empty:

                st.info(
                    "No evaluated experiments found for the latest batch."
                )

            else:

                # ============================================
                # IDENTIFY BASELINE AND CANDIDATE
                # ============================================

                baseline_rows = evaluations[
                    evaluations["experiment_name"]
                    == "FACTOR_ABLATION_BASELINE_None"
                ]

                baseline_row = (
                    baseline_rows.iloc[0]
                    if not baseline_rows.empty
                    else None
                )

                candidate_rows = evaluations[
                    evaluations["experiment_name"]
                    != "FACTOR_ABLATION_BASELINE_None"
                ]

                last_experiment_id = st.session_state.get(
                    "rnd_last_experiment"
                )

                if (
                    last_experiment_id
                    and last_experiment_id
                    in candidate_rows["experiment_id"].values
                ):

                    candidate_row = candidate_rows[
                        candidate_rows["experiment_id"]
                        == last_experiment_id
                    ].iloc[0]

                elif not candidate_rows.empty:

                    candidate_row = candidate_rows.iloc[0]

                else:

                    candidate_row = None

                # ============================================
                # BASELINE VS EXPERIMENT
                # ============================================

                st.subheader("📊 Baseline vs Experiment")

                if (
                    baseline_row is not None
                    and candidate_row is not None
                ):

                    comparison_rows = []

                    metric_definitions = [
                        ("Gross Return %", "gross_return_pct"),
                        ("Net Return %", "net_return_pct"),
                        ("Net CAGR %", "net_cagr_pct"),
                        ("Sharpe", "net_sharpe"),
                        (
                            "Max Drawdown %",
                            "net_max_drawdown_pct",
                        ),
                        (
                            "Win Rate %",
                            "net_win_rate_pct",
                        ),
                        ("Turnover %", "turnover_pct"),
                        (
                            "Avg Weekly Turnover %",
                            "avg_weekly_turnover_pct",
                        ),
                        (
                            "Transaction Cost %",
                            "transaction_cost_pct",
                        ),
                    ]

                    for label, field in metric_definitions:

                        baseline_value = float(
                            baseline_row[field]
                        )

                        candidate_value = float(
                            candidate_row[field]
                        )

                        comparison_rows.append(
                            {
                                "Metric": label,
                                "Baseline": round(
                                    baseline_value,
                                    2,
                                ),
                                "Experiment": round(
                                    candidate_value,
                                    2,
                                ),
                                "Δ": round(
                                    candidate_value
                                    - baseline_value,
                                    2,
                                ),
                            }
                        )

                    comparison_rows.append(
                        {
                            "Metric": "Δ CAGR",
                            "Baseline": 0.00,
                            "Experiment": round(
                                float(
                                    candidate_row[
                                        "delta_cagr_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Δ": round(
                                float(
                                    candidate_row[
                                        "delta_cagr_pct"
                                    ]
                                ),
                                2,
                            ),
                        }
                    )

                    comparison_rows.append(
                        {
                            "Metric": "Δ Sharpe",
                            "Baseline": 0.00,
                            "Experiment": round(
                                float(
                                    candidate_row[
                                        "delta_sharpe"
                                    ]
                                ),
                                2,
                            ),
                            "Δ": round(
                                float(
                                    candidate_row[
                                        "delta_sharpe"
                                    ]
                                ),
                                2,
                            ),
                        }
                    )

                    st.dataframe(
                        pd.DataFrame(comparison_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.caption(
                        f"Baseline: {baseline_row['experiment_name']}  |  "
                        f"Experiment: {candidate_row['experiment_name']}"
                    )

                elif candidate_row is not None:

                    st.warning(
                        "Experiment found, but the standard R&D baseline "
                        "is not available for comparison."
                    )

                # ============================================
                # YEARLY PERFORMANCE
                # ============================================

                st.subheader("📅 Yearly Performance")

                yearly_all = query_duckdb(
                    """
                    SELECT
                        experiment_id,
                        year,
                        return_pct,
                        weeks
                    FROM analytics.main.experiment_yearly_results
                    WHERE experiment_id IN (
                        SELECT experiment_id
                        FROM analytics.main.experiment_evaluations
                        WHERE split_part(experiment_id, '_', 1) = ?
                    )
                    ORDER BY year, experiment_id
                    """,
                    [batch_id],
                )

                if yearly_all.empty:

                    st.info(
                        "No yearly performance data is available."
                    )

                elif (
                    baseline_row is not None
                    and candidate_row is not None
                ):

                    baseline_id = baseline_row["experiment_id"]
                    candidate_id = candidate_row["experiment_id"]

                    yearly_comparison = []

                    years = sorted(
                        yearly_all["year"].unique()
                    )

                    for year in years:

                        base = yearly_all[
                            (
                                yearly_all["experiment_id"]
                                == baseline_id
                            )
                            & (
                                yearly_all["year"]
                                == year
                            )
                        ]

                        candidate = yearly_all[
                            (
                                yearly_all["experiment_id"]
                                == candidate_id
                            )
                            & (
                                yearly_all["year"]
                                == year
                            )
                        ]

                        if base.empty or candidate.empty:
                            continue

                        base_row = base.iloc[0]
                        candidate_year = candidate.iloc[0]

                        baseline_return = float(
                            base_row["return_pct"]
                        )

                        candidate_return = float(
                            candidate_year["return_pct"]
                        )

                        yearly_comparison.append(
                            {
                                "Year": int(year),
                                "Baseline Return %": round(
                                    baseline_return,
                                    2,
                                ),
                                "Experiment Return %": round(
                                    candidate_return,
                                    2,
                                ),
                                "Δ Return %": round(
                                    candidate_return
                                    - baseline_return,
                                    2,
                                ),
                                "Baseline Weeks": safe_int(base_row["weeks"]),
                                "Experiment Weeks": safe_int(candidate_year["weeks"]),
                            }
                        )

                    if yearly_comparison:

                        st.dataframe(
                            pd.DataFrame(
                                yearly_comparison
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )

                    else:

                        st.info(
                            "Yearly comparison is not available "
                            "for the selected baseline and experiment."
                        )

                else:

                    yearly_display = yearly_all.rename(
                        columns={
                            "experiment_id": "Experiment",
                            "year": "Year",
                            "return_pct": "Return %",
                            "weeks": "Weeks",
                        }
                    ).copy()

                    yearly_display["Return %"] = (
                        yearly_display["Return %"]
                        .round(2)
                    )

                    st.dataframe(
                        yearly_display,
                        use_container_width=True,
                        hide_index=True,
                    )

                # ============================================
                # COST & TURNOVER
                # ============================================

                st.subheader("💰 Cost & Turnover")

                cost_rows = []

                for _, row in evaluations.iterrows():

                    cost_rows.append(
                        {
                            "Experiment": row[
                                "experiment_name"
                            ],
                            "Top N": safe_int(row["top_n"]),
                            "Cost Rate %": round(
                                float(
                                    row[
                                        "transaction_cost_rate"
                                    ]
                                )
                                * 100,
                                3,
                            ),
                            "Gross Return %": round(
                                float(
                                    row[
                                        "gross_return_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Net Return %": round(
                                float(
                                    row[
                                        "net_return_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Net CAGR %": round(
                                float(
                                    row[
                                        "net_cagr_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Turnover %": round(
                                float(
                                    row[
                                        "turnover_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Avg Weekly Turnover %": round(
                                float(
                                    row[
                                        "avg_weekly_turnover_pct"
                                    ]
                                ),
                                2,
                            ),
                            "Transaction Cost %": round(
                                float(
                                    row[
                                        "transaction_cost_pct"
                                    ]
                                ),
                                2,
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(cost_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                # ============================================
                # CONFIGURATION COMPARISON
                # ============================================

                st.subheader("⚙️ Configuration Comparison")

                configuration_rows = []

                for _, row in evaluations.iterrows():

                    configuration_rows.append(
                        {
                            "Experiment": row[
                                "experiment_name"
                            ],
                            "Type": row[
                                "experiment_type"
                            ],
                            "Top N": safe_int(row["top_n"]),
                            "Transaction Cost %": round(
                                float(
                                    row[
                                        "transaction_cost_rate"
                                    ]
                                )
                                * 100,
                                3,
                            ),
                            "Start Date": row[
                                "start_date"
                            ],
                            "End Date": row[
                                "end_date"
                            ],
                            "Weeks": safe_int(row["weeks"]),
                            "Status": row[
                                "status"
                            ],
                        }
                    )

                st.dataframe(
                    pd.DataFrame(
                        configuration_rows
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                # ============================================
                # EXPERIMENT DETAIL
                # ============================================

                st.subheader("🔬 Experiment Detail")

                experiment_options = evaluations[
                    [
                        "experiment_id",
                        "experiment_name",
                    ]
                ].drop_duplicates()

                selected_experiment = st.selectbox(
                    "Select experiment",
                    experiment_options[
                        "experiment_id"
                    ].tolist(),
                    format_func=lambda x: (
                        experiment_options.loc[
                            experiment_options[
                                "experiment_id"
                            ]
                            == x,
                            "experiment_name",
                        ].iloc[0]
                    ),
                    key="rnd_experiment",
                )

                selected_eval = evaluations[
                    evaluations["experiment_id"]
                    == selected_experiment
                ].iloc[0]

                experiment = query_duckdb(
                    """
                    SELECT
                        experiment_id,
                        experiment_name,
                        experiment_type,
                        parameter_name,
                        parameter_value,
                        top_n,
                        transaction_cost_rate,
                        group_weights_json,
                        factor_weights_json,
                        status,
                        created_at
                    FROM analytics.main.experiment_runs
                    WHERE experiment_id = ?
                    """,
                    [selected_experiment],
                )

                factors = query_duckdb(
                    """
                    SELECT
                        factor_group,
                        feature_id,
                        weight,
                        direction,
                        enabled
                    FROM analytics.main.experiment_run_factors
                    WHERE experiment_id = ?
                    ORDER BY factor_group, feature_id
                    """,
                    [selected_experiment],
                )

                # ============================================
                # SELECTED EXPERIMENT METADATA
                # ============================================

                if not experiment.empty:

                    exp = experiment.iloc[0]

                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric(
                        "Experiment Type",
                        str(
                            exp[
                                "experiment_type"
                            ]
                        ),
                    )

                    col2.metric(
                        "Top N",
                        int(
                            exp["top_n"]
                        ),
                    )

                    col3.metric(
                        "Net CAGR",
                        f"{float(selected_eval['net_cagr_pct']):.2f}%",
                    )

                    col4.metric(
                        "Sharpe",
                        f"{float(selected_eval['net_sharpe']):.2f}",
                    )

                    metadata = pd.DataFrame(
                        {
                            "Parameter": [
                                "Experiment ID",
                                "Experiment Name",
                                "Experiment Type",
                                "Parameter Name",
                                "Parameter Value",
                                "Top N",
                                "Transaction Cost",
                                "Status",
                                "Created At",
                                "Start Date",
                                "End Date",
                                "Weeks",
                            ],
                            "Value": [
                                exp[
                                    "experiment_id"
                                ],
                                exp[
                                    "experiment_name"
                                ],
                                exp[
                                    "experiment_type"
                                ],
                                exp[
                                    "parameter_name"
                                ],
                                exp[
                                    "parameter_value"
                                ],
                                exp["top_n"],
                                (
                                    f"{float(exp['transaction_cost_rate']) * 100:.3f}%"
                                ),
                                exp["status"],
                                exp["created_at"],
                                selected_eval[
                                    "start_date"
                                ],
                                selected_eval[
                                    "end_date"
                                ],
                                safe_int(selected_eval["weeks"]),
                            ],
                        }
                    )

                    st.dataframe(
                        metadata,
                        use_container_width=True,
                        hide_index=True,
                    )

                # ============================================
                # FACTOR CONFIGURATION
                # ============================================

                if not factors.empty:

                    st.subheader(
                        "🧩 Factor Configuration"
                    )

                    factor_display = factors.copy()

                    factor_display[
                        "Direction"
                    ] = factor_display[
                        "direction"
                    ].map(
                        {
                            1: "Positive",
                            -1: "Negative",
                        }
                    )

                    factor_display[
                        "Weight %"
                    ] = (
                        factor_display[
                            "weight"
                        ]
                        * 100
                    ).round(2)

                    factor_display = factor_display[
                        [
                            "factor_group",
                            "feature_id",
                            "enabled",
                            "Weight %",
                            "Direction",
                        ]
                    ].rename(
                        columns={
                            "factor_group": "Factor Group",
                            "feature_id": "Feature",
                            "enabled": "Enabled",
                        }
                    )

                    st.dataframe(
                        factor_display,
                        use_container_width=True,
                        hide_index=True,
                    )

                # ============================================
                # FUTURE BASELINE DESIGN
                # ============================================

                st.subheader(
                    "🎯 Comparison Baseline"
                )

                if baseline_row is not None:

                    st.info(
                        "Current baseline: "
                        f"{baseline_row['experiment_name']}. "
                        "The R&D review keeps baseline selection "
                        "separate from the experiment itself so a "
                        "future version can allow comparison against "
                        "another validated experiment or production "
                        "configuration."
                    )

                else:

                    st.info(
                        "No standard baseline is available in "
                        "this batch. Future versions can support "
                        "selecting a validated experiment or "
                        "production configuration as the baseline."
                    )

                st.info(
                    "R&D results are for research and human review only. "
                    "Promoting an experiment to production remains a "
                    "deliberate configuration-management decision."
                )

    except Exception as e:

        st.error(f"Unable to load R&D experiments: {e}")
        st.exception(e)


# ============================================================
# CONFIGURATION MANAGER
# ============================================================

with tab_config:

    st.header("Configuration Manager")
    st.caption(
        "View versioned strategy configurations and factor definitions."
    )

    try:
        configurations = query_df(
            """
            SELECT
                configuration_id,
                strategy_id,
                configuration_version,
                strategy_name,
                momentum_weight,
                trend_weight,
                risk_weight,
                drawdown_weight,
                top_n,
                position_weight,
                transaction_cost_rate,
                signal_frequency,
                entry_rule,
                rebalance_rule,
                status,
                configuration_type,
                created_at
            FROM analytics.strategy_config_version
            ORDER BY configuration_id DESC
            """
        )

        if configurations.empty:
            st.info("No strategy configurations available.")

        else:
            selected_config = st.selectbox(
                "Configuration",
                configurations["configuration_id"].tolist(),
                format_func=lambda x: (
                    f"Config {int(x)} — "
                    f"{configurations.loc[configurations['configuration_id'] == x, 'strategy_name'].iloc[0]}"
                ),
                key="config_manager_configuration",
            )

            config = configurations[
                configurations["configuration_id"] == selected_config
            ].iloc[0]

            st.subheader("Configuration Overview")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Configuration ID",
                int(config["configuration_id"]),
            )

            col2.metric(
                "Version",
                int(config["configuration_version"]),
            )

            col3.metric(
                "Top N",
                int(config["top_n"]),
            )

            col4.metric(
                "Status",
                str(config["status"]),
            )

            st.write(
                f"**Strategy:** {config['strategy_id']}"
            )
            st.write(
                f"**Name:** {config['strategy_name']}"
            )
            st.write(
                f"**Type:** {config['configuration_type']}"
            )

            st.subheader("Factor Group Weights")

            group_weights = query_df(
                """
                SELECT
                    factor_group_id,
                    factor_group_name,
                    group_weight,
                    enabled
                FROM analytics.strategy_config_version_factor_group
                WHERE configuration_id = %(configuration_id)s
                ORDER BY factor_group_id
                """,
                params={
                    "configuration_id": selected_config,
                },
            )

            group_display = group_weights.copy()

            group_display["group_weight"] = (
                group_display["group_weight"] * 100
            ).round(2)

            group_display = group_display.rename(
                columns={
                    "factor_group_id": "Factor Group",
                    "factor_group_name": "Name",
                    "group_weight": "Weight %",
                    "enabled": "Enabled",
                }
            )

            st.dataframe(
                group_display,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Factor Weights")

            factors = query_df(
                """
                SELECT
                    factor_group_id,
                    feature_id,
                    feature_weight,
                    direction,
                    enabled
                FROM analytics.strategy_config_version_factor
                WHERE configuration_id = %(configuration_id)s
                ORDER BY factor_group_id, feature_id
                """,
                params={
                    "configuration_id": selected_config,
                },
            )

            factor_display = factors.copy()

            factor_display["feature_weight"] = (
                factor_display["feature_weight"] * 100
            ).round(2)

            factor_display = factor_display.rename(
                columns={
                    "factor_group_id": "Factor Group",
                    "feature_id": "Feature",
                    "feature_weight": "Weight %",
                    "direction": "Direction",
                    "enabled": "Enabled",
                }
            )

            st.dataframe(
                factor_display,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Portfolio & Signal Settings")

            settings = {
                "Position Weight": f"{float(config['position_weight']) * 100:.2f}%",
                "Transaction Cost Rate": f"{float(config['transaction_cost_rate']) * 100:.3f}%",
                "Signal Frequency": config["signal_frequency"],
                "Entry Rule": config["entry_rule"],
                "Rebalance Rule": config["rebalance_rule"],
            }

            st.table(
                {
                    "Setting": list(settings.keys()),
                    "Value": list(settings.values()),
                }
            )

    except Exception as e:
        st.error(
            f"Unable to load configuration manager: {e}"
        )
