import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from db import query_df, query_duckdb


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SAVED_RND_CONFIG_PATH = (
    PROJECT_ROOT / "research" / "rnd_saved_configs.json"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from research.run_experiment import (
    run_custom_experiment,
    DEFAULT_GROUP_WEIGHTS,
    DEFAULT_FACTOR_WEIGHTS,
    FACTOR_GROUPS,
)


# ============================================================
# HELPERS
# ============================================================

def safe_int(value):
    if value is None or pd.isna(value):
        return None
    return int(value)


def safe_float(value, default=0.0):
    if value is None or pd.isna(value):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ============================================================
# R&D SAVED CONFIGURATION HELPERS
# ============================================================

def load_saved_rnd_configs():
    """
    Load persistent R&D configurations from JSON.

    This is intentionally kept in the Streamlit/UI layer.
    It does not modify the research evaluator or database schema.
    """

    if not SAVED_RND_CONFIG_PATH.exists():
        return []

    try:
        with open(
            SAVED_RND_CONFIG_PATH,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        return data

    except Exception:
        return []


def write_saved_rnd_configs(configs):
    """
    Persist R&D configurations to disk.
    """

    SAVED_RND_CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = SAVED_RND_CONFIG_PATH.with_suffix(
        ".json.tmp"
    )

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            configs,
            f,
            indent=2,
            ensure_ascii=False,
        )

    temp_path.replace(
        SAVED_RND_CONFIG_PATH
    )


def find_saved_rnd_config(
    configs,
    name,
):
    for config in configs:

        if str(config.get("name", "")) == str(name):
            return config

    return None


def save_rnd_configuration(
    name,
    group_weights,
    factor_weights,
    factor_enabled,
    top_n,
    transaction_cost_pct,
    baseline_experiment_id,
    existing_created_at=None,
):
    """
    Create or update a named R&D configuration.
    """

    name = str(name).strip()

    if not name:
        raise ValueError(
            "Configuration name cannot be empty."
        )

    configs = load_saved_rnd_configs()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    configuration = {
        "name": name,
        "group_weights": {
            key: float(value)
            for key, value in group_weights.items()
        },
        "factor_weights": {
            key: float(value)
            for key, value in factor_weights.items()
        },
        "factor_enabled": {
            key: bool(value)
            for key, value in factor_enabled.items()
        },
        "top_n": int(top_n),
        "transaction_cost_pct": float(
            transaction_cost_pct
        ),
        "baseline_experiment_id": (
            str(baseline_experiment_id)
            if baseline_experiment_id
            else None
        ),
        "created_at": (
            existing_created_at
            or now
        ),
        "updated_at": now,
    }

    existing_index = None

    for index, existing in enumerate(configs):

        if (
            str(existing.get("name", "")).strip().lower()
            == name.lower()
        ):
            existing_index = index
            break

    if existing_index is None:

        configs.append(configuration)

    else:

        configs[existing_index] = configuration

    write_saved_rnd_configs(configs)

    return configuration


def rename_rnd_configuration(
    old_name,
    new_name,
):
    old_name = str(old_name).strip()
    new_name = str(new_name).strip()

    if not old_name:
        raise ValueError(
            "Current configuration name is empty."
        )

    if not new_name:
        raise ValueError(
            "New configuration name cannot be empty."
        )

    if old_name.lower() == new_name.lower():
        return

    configs = load_saved_rnd_configs()

    old_config = find_saved_rnd_config(
        configs,
        old_name,
    )

    if old_config is None:
        raise ValueError(
            "The selected saved configuration no longer exists."
        )

    existing_new = find_saved_rnd_config(
        configs,
        new_name,
    )

    if existing_new is not None:
        raise ValueError(
            f"A configuration named '{new_name}' already exists."
        )

    old_config["name"] = new_name
    old_config["updated_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    write_saved_rnd_configs(configs)


def delete_rnd_configuration(
    name,
):
    configs = load_saved_rnd_configs()

    filtered = [
        config
        for config in configs
        if str(config.get("name", "")) != str(name)
    ]

    if len(filtered) == len(configs):
        raise ValueError(
            "The selected saved configuration no longer exists."
        )

    write_saved_rnd_configs(filtered)


def apply_saved_rnd_config_to_session(
    config,
):
    """
    Populate Streamlit widget state before the widgets
    are instantiated on the next rerun.
    """

    group_weights = config.get(
        "group_weights",
        {},
    )

    for group in DEFAULT_GROUP_WEIGHTS:

        st.session_state[
            f"rnd_group_{group}"
        ] = safe_float(
            group_weights.get(
                group,
                DEFAULT_GROUP_WEIGHTS[group],
            )
        )

    factor_weights = config.get(
        "factor_weights",
        {},
    )

    factor_enabled = config.get(
        "factor_enabled",
        {},
    )

    for factor in DEFAULT_FACTOR_WEIGHTS:

        st.session_state[
            f"rnd_factor_{factor}"
        ] = safe_float(
            factor_weights.get(
                factor,
                DEFAULT_FACTOR_WEIGHTS[factor],
            )
        )

        st.session_state[
            f"rnd_enabled_{factor}"
        ] = bool(
            factor_enabled.get(
                factor,
                True,
            )
        )

    st.session_state["rnd_top_n"] = int(
        config.get(
            "top_n",
            2,
        )
    )

    st.session_state[
        "rnd_transaction_cost"
    ] = safe_float(
        config.get(
            "transaction_cost_pct",
            0.20,
        ),
        0.20,
    )

    baseline_id = config.get(
        "baseline_experiment_id"
    )

    if baseline_id:
        st.session_state[
            "rnd_selected_baseline"
        ] = baseline_id

    st.session_state[
        "rnd_config_name"
    ] = str(
        config.get(
            "name",
            "",
        )
    )


# ============================================================
# R&D VERDICT
# ============================================================

def generate_rnd_verdict(candidate, baseline):
    """
    Generate a concise rule-based R&D verdict.

    UI-only logic. Research evaluator remains unchanged.
    """

    if candidate is None or baseline is None:

        return {
            "level": "⚪",
            "title": "Comparison unavailable",
            "message": (
                "A complete baseline comparison is not available."
            ),
        }

    cagr_delta = (
        safe_float(candidate["net_cagr_pct"])
        - safe_float(baseline["net_cagr_pct"])
    )

    sharpe_delta = (
        safe_float(candidate["net_sharpe"])
        - safe_float(baseline["net_sharpe"])
    )

    drawdown_delta = (
        safe_float(candidate["net_max_drawdown_pct"])
        - safe_float(baseline["net_max_drawdown_pct"])
    )

    win_rate_delta = (
        safe_float(candidate["net_win_rate_pct"])
        - safe_float(baseline["net_win_rate_pct"])
    )

    turnover_delta = (
        safe_float(candidate["turnover_pct"])
        - safe_float(baseline["turnover_pct"])
    )

    cost_delta = (
        safe_float(candidate["transaction_cost_pct"])
        - safe_float(baseline["transaction_cost_pct"])
    )

    # --------------------------------------------------------
    # Strong improvement
    # --------------------------------------------------------

    if (
        cagr_delta >= 1.0
        and sharpe_delta >= 0.10
        and drawdown_delta >= -0.50
    ):

        return {
            "level": "🟢",
            "title": "Strong improvement",
            "message": (
                f"Higher CAGR and Sharpe with broadly improved "
                f"drawdown versus baseline "
                f"({cagr_delta:+.2f}% CAGR, "
                f"{sharpe_delta:+.2f} Sharpe, "
                f"{drawdown_delta:+.2f}% drawdown)."
            ),
        }

    # --------------------------------------------------------
    # Improvement with higher risk
    # --------------------------------------------------------

    if (
        cagr_delta >= 1.0
        and sharpe_delta >= 0.05
        and drawdown_delta < -0.50
    ):

        return {
            "level": "🟡",
            "title": "Improvement with higher risk",
            "message": (
                f"CAGR and Sharpe improved, but maximum drawdown "
                f"became worse ({drawdown_delta:+.2f}%)."
            ),
        }

    # --------------------------------------------------------
    # Higher return, weaker risk-adjusted performance
    # --------------------------------------------------------

    if (
        cagr_delta >= 1.0
        and sharpe_delta <= -0.10
    ):

        return {
            "level": "🟡",
            "title": "Higher return, weaker risk-adjusted performance",
            "message": (
                f"CAGR improved by {cagr_delta:+.2f}%, "
                f"but Sharpe weakened by {sharpe_delta:+.2f}."
            ),
        }

    # --------------------------------------------------------
    # Clear underperformance
    # --------------------------------------------------------

    if (
        cagr_delta <= -1.0
        and sharpe_delta <= -0.10
    ):

        return {
            "level": "🔴",
            "title": "Underperforms baseline",
            "message": (
                f"Lower CAGR ({cagr_delta:+.2f}%) and "
                f"lower Sharpe ({sharpe_delta:+.2f}) "
                f"do not justify the experimental configuration."
            ),
        }

    # --------------------------------------------------------
    # Small positive improvement
    # --------------------------------------------------------

    if (
        cagr_delta > 0
        and sharpe_delta > 0
    ):

        return {
            "level": "🟡",
            "title": "Promising but requires validation",
            "message": (
                f"Performance improved, but the difference is "
                f"relatively small "
                f"({cagr_delta:+.2f}% CAGR, "
                f"{sharpe_delta:+.2f} Sharpe)."
            ),
        }

    # --------------------------------------------------------
    # No meaningful improvement
    # --------------------------------------------------------

    if (
        abs(cagr_delta) <= 1.0
        and abs(sharpe_delta) <= 0.10
        and abs(drawdown_delta) <= 1.0
    ):

        return {
            "level": "⚪",
            "title": "No meaningful improvement",
            "message": (
                "Performance is broadly similar to the baseline."
            ),
        }

    # --------------------------------------------------------
    # Default
    # --------------------------------------------------------

    return {
        "level": "🟡",
        "title": "Mixed result",
        "message": (
            "Some metrics improved, but the overall result "
            "is inconclusive."
        ),
    }


def render_rnd_result_summary(
    candidate,
    baseline,
    saved_config_name=None,
):
    """
    Render the primary R&D result summary.
    """

    if candidate is None:

        st.info(
            "No experiment result is available."
        )

        return

    verdict = generate_rnd_verdict(
        candidate,
        baseline,
    )

    experiment_name = str(
        candidate["experiment_name"]
    )

    if baseline is not None:

        baseline_name = str(
            baseline["experiment_name"]
        )

    else:

        baseline_name = "Unavailable"

    st.subheader(
        "📊 Experiment Result"
    )

    st.markdown(
        f"### {experiment_name}"
    )

    if saved_config_name:

        st.caption(
            f"Saved configuration: **{saved_config_name}**  |  "
            f"Compared with: {baseline_name}"
        )

    else:

        st.caption(
            f"Compared with: {baseline_name}"
        )

    # --------------------------------------------------------
    # Primary metrics
    # --------------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    cagr_delta = None
    sharpe_delta = None
    drawdown_delta = None
    win_rate_delta = None

    if baseline is not None:

        cagr_delta = (
            safe_float(candidate["net_cagr_pct"])
            - safe_float(baseline["net_cagr_pct"])
        )

        sharpe_delta = (
            safe_float(candidate["net_sharpe"])
            - safe_float(baseline["net_sharpe"])
        )

        drawdown_delta = (
            safe_float(candidate["net_max_drawdown_pct"])
            - safe_float(baseline["net_max_drawdown_pct"])
        )

        win_rate_delta = (
            safe_float(candidate["net_win_rate_pct"])
            - safe_float(baseline["net_win_rate_pct"])
        )

    col1.metric(
        "Net CAGR",
        f"{safe_float(candidate['net_cagr_pct']):.2f}%",
        (
            f"{cagr_delta:+.2f}%"
            if cagr_delta is not None
            else None
        ),
    )

    col2.metric(
        "Sharpe",
        f"{safe_float(candidate['net_sharpe']):.2f}",
        (
            f"{sharpe_delta:+.2f}"
            if sharpe_delta is not None
            else None
        ),
    )

    col3.metric(
        "Max Drawdown",
        f"{safe_float(candidate['net_max_drawdown_pct']):.2f}%",
        (
            f"{drawdown_delta:+.2f}%"
            if drawdown_delta is not None
            else None
        ),
    )

    col4.metric(
        "Win Rate",
        f"{safe_float(candidate['net_win_rate_pct']):.2f}%",
        (
            f"{win_rate_delta:+.2f}%"
            if win_rate_delta is not None
            else None
        ),
    )

    # --------------------------------------------------------
    # Secondary metrics
    # --------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Turnover",
        f"{safe_float(candidate['turnover_pct']):.2f}%",
    )

    col2.metric(
        "Transaction Cost",
        f"{safe_float(candidate['transaction_cost_pct']):.2f}%",
    )

    col3.metric(
        "Weeks",
        safe_int(candidate["weeks"]),
    )

    # --------------------------------------------------------
    # Verdict
    # --------------------------------------------------------

    st.markdown("---")

    st.markdown(
        f"### {verdict['level']} {verdict['title']}"
    )

    st.info(
        verdict["message"]
    )

    # --------------------------------------------------------
    # Cost / turnover qualifier
    # --------------------------------------------------------

    if baseline is not None:

        turnover_delta = (
            safe_float(candidate["turnover_pct"])
            - safe_float(baseline["turnover_pct"])
        )

        cost_delta = (
            safe_float(candidate["transaction_cost_pct"])
            - safe_float(baseline["transaction_cost_pct"])
        )

        if (
            turnover_delta > 0
            or cost_delta > 0
        ):

            qualifiers = []

            if turnover_delta > 0:

                qualifiers.append(
                    f"turnover {turnover_delta:+.2f}%"
                )

            if cost_delta > 0:

                qualifiers.append(
                    f"transaction cost {cost_delta:+.2f}%"
                )

            st.caption(
                "Cost / turnover consideration: "
                + ", ".join(qualifiers)
                + "."
            )


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Quant Investment Platform",
    page_icon="📈",
    layout="wide",
)

st.title(
    "Quant Investment Platform"
)

st.caption(
    "Personal quantitative investing dashboard"
)


tab_status, tab_signals, tab_performance, tab_rnd, tab_config = (
    st.tabs(
        [
            "🏠 System Status",
            "📊 Signal Review",
            "📈 Strategy Performance",
            "🧪 R&D",
            "⚙️ Configuration Manager",
        ]
    )
)


# ============================================================
# SYSTEM STATUS
# ============================================================

with tab_status:

    st.header(
        "System Status"
    )

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

        st.success(
            "PostgreSQL connection: Healthy"
        )

    except Exception as e:

        st.error(
            f"Unable to connect to PostgreSQL: {e}"
        )


# ============================================================
# WEEKLY SIGNAL REVIEW
# ============================================================

with tab_signals:

    st.header(
        "Weekly Signal Review"
    )

    try:

        signal_dates = query_df(
            """
            SELECT DISTINCT signal_date
            FROM analytics.weekly_signals_v2
            ORDER BY signal_date DESC
            """
        )

        if signal_dates.empty:

            st.info(
                "No weekly signals available."
            )

        else:

            selected_date = st.selectbox(
                "Signal Week",
                signal_dates[
                    "signal_date"
                ].tolist(),
                format_func=lambda x: str(x),
            )

            strategies = query_df(
                """
                SELECT DISTINCT strategy_id
                FROM analytics.weekly_signals_v2
                WHERE signal_date = %(signal_date)s
                ORDER BY strategy_id
                """,
                params={
                    "signal_date": selected_date,
                },
            )

            selected_strategy = st.selectbox(
                "Strategy",
                strategies[
                    "strategy_id"
                ].tolist(),
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
                configurations[
                    "configuration_id"
                ].tolist(),
                format_func=lambda x: (
                    f"Top {int(x)}"
                ),
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

                execution_date = (
                    signals["execution_date"].iloc[0]
                )

                st.caption(
                    f"Signal date: {selected_date}  |  "
                    f"Execution date: {execution_date}"
                )

                buy_count = int(
                    (
                        signals["signal"]
                        == "BUY"
                    ).sum()
                )

                hold_count = int(
                    (
                        signals["signal"]
                        == "HOLD"
                    ).sum()
                )

                sell_count = int(
                    (
                        signals["signal"]
                        == "SELL"
                    ).sum()
                )

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "BUY",
                    buy_count,
                )

                col2.metric(
                    "HOLD",
                    hold_count,
                )

                col3.metric(
                    "SELL",
                    sell_count,
                )

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
                    display[
                        "Previous Weight"
                    ].fillna(0)
                    * 100
                ).round(2).astype(str) + "%"

                display["Target Weight"] = (
                    display[
                        "Target Weight"
                    ].fillna(0)
                    * 100
                ).round(2).astype(str) + "%"

                display["Score"] = (
                    display["Score"].round(4)
                )

                st.dataframe(
                    display,
                    use_container_width=True,
                    hide_index=True,
                )

    except Exception as e:

        st.error(
            f"Unable to load weekly signals: {e}"
        )


# ============================================================
# STRATEGY PERFORMANCE
# ============================================================

with tab_performance:

    st.header(
        "Strategy Performance"
    )

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

            st.info(
                "No strategy performance data available."
            )

        else:

            strategies = (
                performance[
                    "strategy_id"
                ]
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
                performance["strategy_id"]
                == selected_perf_strategy
            ].copy()

            perf["Configuration"] = (
                "Top "
                + perf[
                    "configuration_id"
                ].astype(int).astype(str)
            )

            st.subheader(
                "Net Performance"
            )

            for _, row in perf.iterrows():

                st.markdown(
                    f"**{row['Configuration']}**"
                )

                col1, col2, col3, col4, col5 = (
                    st.columns(5)
                )

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

            st.subheader(
                "Configuration Comparison"
            )

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

            comparison[
                numeric_columns
            ] = comparison[
                numeric_columns
            ].round(2)

            st.dataframe(
                comparison,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader(
                "Gross vs Net"
            )

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

        st.error(
            f"Unable to load strategy performance: {e}"
        )


# ============================================================
# R&D / EXPERIMENT REVIEW
# ============================================================

with tab_rnd:

    st.header(
        "🧪 R&D Workbench"
    )

    st.caption(
        "Research workspace for testing factor configurations, "
        "saving named research configurations, comparing experiments "
        "against a baseline, and reviewing whether an experiment "
        "is worth further validation."
    )

    # ========================================================
    # LOAD SAVED CONFIGURATIONS
    # ========================================================

    saved_configs = load_saved_rnd_configs()

    saved_config_names = [
        str(config.get("name", "Unnamed"))
        for config in saved_configs
    ]

    st.subheader(
        "💾 Saved R&D Configurations"
    )

    saved_col1, saved_col2 = st.columns(
        [2, 1]
    )

    with saved_col1:

        saved_selection_options = [
            "— Current / New Configuration —"
        ] + saved_config_names

        selected_saved_config = st.selectbox(
            "Saved configuration",
            saved_selection_options,
            key="rnd_saved_config_selector",
        )

    with saved_col2:

        st.text_input(
            "Configuration name",
            key="rnd_config_name",
            placeholder="e.g. Trend Heavy V1",
        )

    saved_action_col1, saved_action_col2, saved_action_col3, saved_action_col4 = (
        st.columns(4)
    )

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    with saved_action_col1:

        load_saved = st.button(
            "📂 Load Configuration",
            use_container_width=True,
            key="rnd_load_saved",
        )

    if load_saved:

        if (
            selected_saved_config
            == "— Current / New Configuration —"
        ):

            st.warning(
                "Select a saved configuration first."
            )

        else:

            selected_config_object = (
                find_saved_rnd_config(
                    saved_configs,
                    selected_saved_config,
                )
            )

            if selected_config_object is None:

                st.error(
                    "The selected saved configuration could not be found."
                )

            else:

                apply_saved_rnd_config_to_session(
                    selected_config_object
                )

                st.session_state[
                    "rnd_selected_saved_config"
                ] = selected_saved_config

                st.success(
                    f"Loaded configuration: "
                    f"{selected_saved_config}"
                )

                st.rerun()

    # --------------------------------------------------------
    # Save / Update
    # --------------------------------------------------------

    with saved_action_col2:

        save_configuration_button = st.button(
            "💾 Save Configuration",
            type="primary",
            use_container_width=True,
            key="rnd_save_configuration",
        )

    # --------------------------------------------------------
    # Rename
    # --------------------------------------------------------

    with saved_action_col3:

        rename_configuration_button = st.button(
            "✏️ Rename",
            use_container_width=True,
            key="rnd_rename_configuration",
        )

    # --------------------------------------------------------
    # Delete
    # --------------------------------------------------------

    with saved_action_col4:

        delete_configuration_button = st.button(
            "🗑️ Delete",
            use_container_width=True,
            key="rnd_delete_configuration",
        )

    # ========================================================
    # R&D EXPERIMENT SETUP
    # ========================================================

    st.divider()

    st.subheader(
        "⚙️ Experiment Configuration"
    )

    # ========================================================
    # FACTOR GROUP WEIGHTS
    # ========================================================

    with st.expander(
        "⚖️ Factor Group Weights",
        expanded=True,
    ):

        group_cols = st.columns(4)

        group_weights = {}

        group_labels = {
            "MOMENTUM": "Momentum",
            "TREND": "Trend",
            "RISK": "Risk",
            "DRAWDOWN": "Drawdown",
        }

        for col, group in zip(
            group_cols,
            DEFAULT_GROUP_WEIGHTS,
        ):

            group_weights[group] = col.number_input(
                group_labels[group],
                min_value=0.0,
                max_value=1.0,
                value=float(
                    DEFAULT_GROUP_WEIGHTS[group]
                ),
                step=0.01,
                format="%.2f",
                key=f"rnd_group_{group}",
            )

        group_total = sum(
            group_weights.values()
        )

        if group_total <= 0:

            st.error(
                "At least one factor group must have a weight greater than zero."
            )

        st.caption(
            f"Group weight total: {group_total:.2f} "
            "(the research engine normalizes weights before scoring)"
        )

    # ========================================================
    # INDIVIDUAL FACTORS
    # ========================================================

    with st.expander(
        "🔬 Individual Factor Weights",
        expanded=False,
    ):

        factor_weights = {}
        factor_enabled = {}

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

            st.markdown(
                f"**{group_labels[group]}**"
            )

            factor_cols = st.columns(
                len(FACTOR_GROUPS[group])
            )

            for col, factor in zip(
                factor_cols,
                FACTOR_GROUPS[group],
            ):

                enabled = col.checkbox(
                    "Enabled",
                    value=True,
                    key=f"rnd_enabled_{factor}",
                )

                factor_enabled[factor] = enabled

                if enabled:

                    factor_weights[factor] = (
                        col.number_input(
                            factor_labels[factor],
                            min_value=0.0,
                            max_value=1.0,
                            value=float(
                                DEFAULT_FACTOR_WEIGHTS[
                                    factor
                                ]
                            ),
                            step=0.01,
                            format="%.2f",
                            key=f"rnd_factor_{factor}",
                        )
                    )

                else:

                    factor_weights[factor] = 0.0

    # ========================================================
    # BACKTEST SETTINGS
    # ========================================================

    with st.expander(
        "⚙️ Backtest Settings",
        expanded=True,
    ):

        settings_col1, settings_col2 = (
            st.columns(2)
        )

        top_n = settings_col1.number_input(
            "Top N positions",
            min_value=1,
            max_value=20,
            value=2,
            step=1,
            key="rnd_top_n",
        )

        transaction_cost_pct = (
            settings_col2.number_input(
                "Transaction cost (%)",
                min_value=0.0,
                max_value=5.0,
                value=0.20,
                step=0.05,
                format="%.2f",
                key="rnd_transaction_cost",
            )
        )

        transaction_cost_rate = (
            transaction_cost_pct / 100.0
        )

    # ========================================================
    # SAVE CONFIGURATION
    # ========================================================

    if save_configuration_button:

        configuration_name = (
            st.session_state.get(
                "rnd_config_name",
                "",
            )
            .strip()
        )

        if not configuration_name:

            st.error(
                "Enter a configuration name before saving."
            )

        elif group_total <= 0:

            st.error(
                "Cannot save configuration: "
                "all factor-group weights are zero."
            )

        elif not any(
            weight > 0
            for weight in factor_weights.values()
        ):

            st.error(
                "Cannot save configuration: "
                "at least one factor must be enabled."
            )

        else:

            try:

                save_rnd_configuration(
                    name=configuration_name,
                    group_weights=group_weights,
                    factor_weights=factor_weights,
                    factor_enabled=factor_enabled,
                    top_n=int(top_n),
                    transaction_cost_pct=(
                        transaction_cost_pct
                    ),
                    baseline_experiment_id=(
                        st.session_state.get(
                            "rnd_selected_baseline"
                        )
                    ),
                )

                st.session_state[
                    "rnd_selected_saved_config"
                ] = configuration_name

                st.success(
                    f"Configuration saved: "
                    f"{configuration_name}"
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"Unable to save configuration: {e}"
                )

    # ========================================================
    # RENAME CONFIGURATION
    # ========================================================

    if rename_configuration_button:

        if (
            selected_saved_config
            == "— Current / New Configuration —"
        ):

            st.warning(
                "Select a saved configuration to rename."
            )

        else:

            new_name = (
                st.session_state.get(
                    "rnd_config_name",
                    "",
                )
                .strip()
            )

            if not new_name:

                st.error(
                    "Enter the new configuration name."
                )

            else:

                try:

                    rename_rnd_configuration(
                        selected_saved_config,
                        new_name,
                    )

                    st.session_state[
                        "rnd_config_name"
                    ] = new_name

                    st.success(
                        f"Configuration renamed to: "
                        f"{new_name}"
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Unable to rename configuration: {e}"
                    )

    # ========================================================
    # DELETE CONFIGURATION
    # ========================================================

    if delete_configuration_button:

        if (
            selected_saved_config
            == "— Current / New Configuration —"
        ):

            st.warning(
                "Select a saved configuration to delete."
            )

        else:

            try:

                delete_rnd_configuration(
                    selected_saved_config
                )

                st.session_state[
                    "rnd_config_name"
                ] = ""

                st.success(
                    f"Deleted configuration: "
                    f"{selected_saved_config}"
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"Unable to delete configuration: {e}"
                )

    # ========================================================
    # R&D BASELINE SELECTION
    # ========================================================

    st.divider()

    st.subheader(
        "🎯 Comparison Baseline"
    )

    baseline_options_df = query_duckdb(
        """
        SELECT
            experiment_id,
            experiment_type,
            experiment_name,
            top_n,
            transaction_cost_rate,
            status,
            created_at
        FROM analytics.main.experiment_runs
        WHERE status = 'COMPLETED'
          AND experiment_type = 'FACTOR_ABLATION'
        ORDER BY created_at DESC
        """
    )

    if baseline_options_df.empty:

        st.error(
            "No completed experiments are available "
            "for baseline selection."
        )

        selected_baseline_experiment_id = None

    else:

        baseline_options_df = (
            baseline_options_df.copy()
        )

        baseline_options_df[
            "display_name"
        ] = (
            baseline_options_df[
                "experiment_name"
            ]
            + " | "
            + baseline_options_df[
                "experiment_id"
            ]
        )

        baseline_ids = (
            baseline_options_df[
                "experiment_id"
            ].tolist()
        )

        baseline_labels = dict(
            zip(
                baseline_options_df[
                    "experiment_id"
                ],
                baseline_options_df[
                    "display_name"
                ],
            )
        )

        default_baseline_rows = (
            baseline_options_df[
                baseline_options_df[
                    "experiment_name"
                ]
                == "FACTOR_ABLATION_BASELINE_None"
            ]
        )

        if not default_baseline_rows.empty:

            default_baseline_id = (
                default_baseline_rows.iloc[0][
                    "experiment_id"
                ]
            )

        else:

            default_baseline_id = (
                baseline_ids[-1]
            )

        session_baseline = (
            st.session_state.get(
                "rnd_selected_baseline"
            )
        )

        if (
            session_baseline
            and session_baseline in baseline_ids
        ):

            default_baseline_id = (
                session_baseline
            )

        default_baseline_index = (
            baseline_ids.index(
                default_baseline_id
            )
            if default_baseline_id
            in baseline_ids
            else 0
        )

        selected_baseline_experiment_id = (
            st.selectbox(
                "Baseline Experiment",
                options=baseline_ids,
                index=default_baseline_index,
                format_func=lambda x:
                    baseline_labels.get(x, x),
                key="rnd_selected_baseline",
            )
        )

        selected_baseline_row = (
            baseline_options_df[
                baseline_options_df[
                    "experiment_id"
                ]
                == selected_baseline_experiment_id
            ]
        )

        if not selected_baseline_row.empty:

            baseline_display_row = (
                selected_baseline_row.iloc[0]
            )

            baseline_info_col1, baseline_info_col2, baseline_info_col3 = (
                st.columns(3)
            )

            baseline_info_col1.metric(
                "Baseline Top N",
                safe_int(
                    baseline_display_row["top_n"]
                ),
            )

            baseline_info_col2.metric(
                "Baseline Cost",
                f"{safe_float(baseline_display_row['transaction_cost_rate']):.2%}",
            )

            baseline_info_col3.metric(
                "Baseline Type",
                str(
                    baseline_display_row[
                        "experiment_type"
                    ]
                ),
            )

    st.caption(
        "The selected baseline is used as the reference "
        "configuration for this R&D run. Your custom configuration "
        "is evaluated against this baseline."
    )

    # ========================================================
    # RUN EXPERIMENT
    # ========================================================

    run_rnd = st.button(
        "▶ Run R&D Experiment",
        type="primary",
        use_container_width=True,
        key="run_custom_rnd",
    )

    if run_rnd:

        if group_total <= 0:

            st.error(
                "Cannot run experiment: "
                "all factor-group weights are zero."
            )

        elif not any(
            weight > 0
            for weight in factor_weights.values()
        ):

            st.error(
                "Cannot run experiment: "
                "at least one factor must be enabled."
            )

        elif selected_baseline_experiment_id is None:

            st.error(
                "Cannot run experiment: "
                "a baseline experiment is required."
            )

        else:

            try:

                with st.spinner(
                    "Running R&D experiment and evaluating results..."
                ):

                    experiment_id = (
                        run_custom_experiment(
                            group_weights=group_weights,
                            factor_weights=factor_weights,
                            top_n=int(top_n),
                            transaction_cost_rate=(
                                transaction_cost_rate
                            ),
                            baseline_experiment_id=(
                                selected_baseline_experiment_id
                            ),
                        )
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
                    f"R&D experiment completed: "
                    f"{experiment_id}"
                )

                st.session_state[
                    "rnd_last_experiment"
                ] = experiment_id

                st.session_state[
                    "rnd_last_saved_config"
                ] = (
                    st.session_state.get(
                        "rnd_config_name",
                        "",
                    ).strip()
                    or None
                )

                st.session_state[
                    "rnd_evaluation_output"
                ] = evaluation.stdout

                st.rerun()

            except subprocess.CalledProcessError as e:

                st.error(
                    "R&D experiment was created, "
                    "but evaluation failed."
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
                SELECT MAX(
                    split_part(
                        experiment_id,
                        '_',
                        1
                    )
                )
                FROM analytics.main.experiment_runs
            )
            GROUP BY split_part(
                experiment_id,
                '_',
                1
            )
            """
        )

        if batch_info.empty:

            st.info(
                "No R&D experiments available."
            )

        else:

            batch = batch_info.iloc[0]

            batch_id = str(
                batch["batch_id"]
            )

            # ------------------------------------------------
            # Latest batch
            # ------------------------------------------------

            with st.expander(
                "📦 Latest R&D Batch",
                expanded=False,
            ):

                col1, col2, col3, col4 = (
                    st.columns(4)
                )

                col1.metric(
                    "Batch",
                    batch_id,
                )

                col2.metric(
                    "Experiments",
                    int(
                        batch[
                            "experiment_count"
                        ]
                    ),
                )

                col3.metric(
                    "Completed",
                    int(
                        batch[
                            "completed_count"
                        ]
                    ),
                )

                col4.metric(
                    "Non-completed",
                    int(
                        batch[
                            "non_completed_count"
                        ]
                    ),
                )

                st.caption(
                    f"Batch created: "
                    f"{batch['batch_created_at']}"
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
                WHERE split_part(
                    e.experiment_id,
                    '_',
                    1
                ) = ?
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
                    "No evaluated experiments found "
                    "for the latest batch."
                )

            else:

                # ============================================
                # IDENTIFY BASELINE AND CANDIDATE
                # ============================================

                baseline_rows = evaluations[
                    evaluations[
                        "experiment_name"
                    ]
                    == "FACTOR_ABLATION_BASELINE_None"
                ]

                baseline_row = (
                    baseline_rows.iloc[0]
                    if not baseline_rows.empty
                    else None
                )

                candidate_rows = evaluations[
                    evaluations[
                        "experiment_name"
                    ]
                    != "FACTOR_ABLATION_BASELINE_None"
                ]

                last_experiment_id = (
                    st.session_state.get(
                        "rnd_last_experiment"
                    )
                )

                if (
                    last_experiment_id
                    and last_experiment_id
                    in candidate_rows[
                        "experiment_id"
                    ].values
                ):

                    candidate_row = (
                        candidate_rows[
                            candidate_rows[
                                "experiment_id"
                            ]
                            == last_experiment_id
                        ].iloc[0]
                    )

                elif not candidate_rows.empty:

                    candidate_row = (
                        candidate_rows.iloc[0]
                    )

                else:

                    candidate_row = None

                saved_config_name = (
                    st.session_state.get(
                        "rnd_last_saved_config"
                    )
                )

                # ============================================
                # PRIMARY EXPERIMENT RESULT
                # ============================================

                render_rnd_result_summary(
                    candidate_row,
                    baseline_row,
                    saved_config_name,
                )

                # ============================================
                # REVIEW TABS
                # ============================================

                review_performance, review_why, review_details = (
                    st.tabs(
                        [
                            "📈 Performance",
                            "🔬 Why It Changed",
                            "📋 Experiment Details",
                        ]
                    )
                )

                # ========================================================
                # PERFORMANCE
                # ========================================================

                with review_performance:

                    # ------------------------------------------------
                    # Detailed comparison
                    # ------------------------------------------------

                    with st.expander(
                        "📊 Detailed Baseline vs Experiment Comparison",
                        expanded=False,
                    ):

                        if (
                            baseline_row is not None
                            and candidate_row is not None
                        ):

                            comparison_rows = []

                            metric_definitions = [
                                (
                                    "Gross Return %",
                                    "gross_return_pct",
                                ),
                                (
                                    "Net Return %",
                                    "net_return_pct",
                                ),
                                (
                                    "Net CAGR %",
                                    "net_cagr_pct",
                                ),
                                (
                                    "Sharpe",
                                    "net_sharpe",
                                ),
                                (
                                    "Max Drawdown %",
                                    "net_max_drawdown_pct",
                                ),
                                (
                                    "Win Rate %",
                                    "net_win_rate_pct",
                                ),
                                (
                                    "Turnover %",
                                    "turnover_pct",
                                ),
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

                                baseline_value = safe_float(
                                    baseline_row[field]
                                )

                                candidate_value = safe_float(
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
                                        safe_float(
                                            candidate_row[
                                                "delta_cagr_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                    "Δ": round(
                                        safe_float(
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
                                        safe_float(
                                            candidate_row[
                                                "delta_sharpe"
                                            ]
                                        ),
                                        2,
                                    ),
                                    "Δ": round(
                                        safe_float(
                                            candidate_row[
                                                "delta_sharpe"
                                            ]
                                        ),
                                        2,
                                    ),
                                }
                            )

                            st.dataframe(
                                pd.DataFrame(
                                    comparison_rows
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )

                            st.caption(
                                f"Baseline: "
                                f"{baseline_row['experiment_name']}  |  "
                                f"Experiment: "
                                f"{candidate_row['experiment_name']}"
                            )

                        elif candidate_row is not None:

                            st.warning(
                                "Experiment found, but the standard "
                                "R&D baseline is not available "
                                "for comparison."
                            )

                        else:

                            st.info(
                                "No candidate experiment is available."
                            )

                    # ------------------------------------------------
                    # Yearly performance
                    # ------------------------------------------------

                    st.subheader(
                        "📅 Yearly Performance"
                    )

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
                            WHERE split_part(
                                experiment_id,
                                '_',
                                1
                            ) = ?
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

                        baseline_id = (
                            baseline_row[
                                "experiment_id"
                            ]
                        )

                        candidate_id = (
                            candidate_row[
                                "experiment_id"
                            ]
                        )

                        yearly_comparison = []

                        years = sorted(
                            yearly_all[
                                "year"
                            ].unique()
                        )

                        for year in years:

                            base = yearly_all[
                                (
                                    yearly_all[
                                        "experiment_id"
                                    ]
                                    == baseline_id
                                )
                                & (
                                    yearly_all[
                                        "year"
                                    ]
                                    == year
                                )
                            ]

                            candidate = yearly_all[
                                (
                                    yearly_all[
                                        "experiment_id"
                                    ]
                                    == candidate_id
                                )
                                & (
                                    yearly_all[
                                        "year"
                                    ]
                                    == year
                                )
                            ]

                            if (
                                base.empty
                                or candidate.empty
                            ):
                                continue

                            base_row = base.iloc[0]

                            candidate_year = (
                                candidate.iloc[0]
                            )

                            baseline_return = (
                                safe_float(
                                    base_row[
                                        "return_pct"
                                    ]
                                )
                            )

                            candidate_return = (
                                safe_float(
                                    candidate_year[
                                        "return_pct"
                                    ]
                                )
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
                                    "Baseline Weeks": safe_int(
                                        base_row[
                                            "weeks"
                                        ]
                                    ),
                                    "Experiment Weeks": safe_int(
                                        candidate_year[
                                            "weeks"
                                        ]
                                    ),
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

                        yearly_display = (
                            yearly_all.rename(
                                columns={
                                    "experiment_id": "Experiment",
                                    "year": "Year",
                                    "return_pct": "Return %",
                                    "weeks": "Weeks",
                                }
                            ).copy()
                        )

                        yearly_display[
                            "Return %"
                        ] = (
                            yearly_display[
                                "Return %"
                            ].round(2)
                        )

                        st.dataframe(
                            yearly_display,
                            use_container_width=True,
                            hide_index=True,
                        )

                    # ------------------------------------------------
                    # Cost & turnover
                    # ------------------------------------------------

                    st.subheader(
                        "💰 Cost & Turnover"
                    )

                    cost_rows = []

                    for _, row in evaluations.iterrows():

                        cost_rows.append(
                            {
                                "Experiment":
                                    row[
                                        "experiment_name"
                                    ],
                                "Top N":
                                    safe_int(
                                        row["top_n"]
                                    ),
                                "Cost Rate %":
                                    round(
                                        safe_float(
                                            row[
                                                "transaction_cost_rate"
                                            ]
                                        )
                                        * 100,
                                        3,
                                    ),
                                "Gross Return %":
                                    round(
                                        safe_float(
                                            row[
                                                "gross_return_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                "Net Return %":
                                    round(
                                        safe_float(
                                            row[
                                                "net_return_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                "Net CAGR %":
                                    round(
                                        safe_float(
                                            row[
                                                "net_cagr_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                "Turnover %":
                                    round(
                                        safe_float(
                                            row[
                                                "turnover_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                "Avg Weekly Turnover %":
                                    round(
                                        safe_float(
                                            row[
                                                "avg_weekly_turnover_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                                "Transaction Cost %":
                                    round(
                                        safe_float(
                                            row[
                                                "transaction_cost_pct"
                                            ]
                                        ),
                                        2,
                                    ),
                            }
                        )

                    st.dataframe(
                        pd.DataFrame(
                            cost_rows
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                # ========================================================
                # WHY IT CHANGED
                # ========================================================

                with review_why:

                    st.caption(
                        "This section explains what changed in the "
                        "factor configuration between the selected "
                        "baseline and candidate."
                    )

                    comparison_experiments = query_duckdb(
                        """
                        SELECT
                            r.experiment_id,
                            r.experiment_type,
                            r.experiment_name,
                            r.top_n,
                            r.transaction_cost_rate,
                            r.status,
                            r.created_at
                        FROM analytics.main.experiment_runs r
                        WHERE r.status = 'COMPLETED'
                        ORDER BY r.created_at DESC
                        """
                    )

                    if comparison_experiments.empty:

                        st.info(
                            "No completed experiments are available "
                            "for factor comparison."
                        )

                    else:

                        comparison_experiments = (
                            comparison_experiments.copy()
                        )

                        comparison_experiments[
                            "display_name"
                        ] = (
                            comparison_experiments[
                                "experiment_name"
                            ]
                            + " | "
                            + comparison_experiments[
                                "experiment_id"
                            ]
                        )

                        custom_candidates = (
                            comparison_experiments[
                                comparison_experiments[
                                    "experiment_type"
                                ]
                                == "CUSTOM_RND"
                            ]
                        )

                        if not custom_candidates.empty:

                            default_candidate_id = (
                                custom_candidates.iloc[0][
                                    "experiment_id"
                                ]
                            )

                        else:

                            default_candidate_id = (
                                comparison_experiments.iloc[0][
                                    "experiment_id"
                                ]
                            )

                        baseline_candidates = (
                            comparison_experiments[
                                comparison_experiments[
                                    "experiment_name"
                                ]
                                == "FACTOR_ABLATION_BASELINE_None"
                            ]
                        )

                        if not baseline_candidates.empty:

                            default_comparison_baseline_id = (
                                baseline_candidates.iloc[0][
                                    "experiment_id"
                                ]
                            )

                        else:

                            default_comparison_baseline_id = (
                                comparison_experiments.iloc[-1][
                                    "experiment_id"
                                ]
                            )

                        option_ids = (
                            comparison_experiments[
                                "experiment_id"
                            ].tolist()
                        )

                        option_labels = dict(
                            zip(
                                comparison_experiments[
                                    "experiment_id"
                                ],
                                comparison_experiments[
                                    "display_name"
                                ],
                            )
                        )

                        baseline_index = (
                            option_ids.index(
                                default_comparison_baseline_id
                            )
                            if (
                                default_comparison_baseline_id
                                in option_ids
                            )
                            else 0
                        )

                        candidate_index = (
                            option_ids.index(
                                default_candidate_id
                            )
                            if (
                                default_candidate_id
                                in option_ids
                            )
                            else 0
                        )

                        selector_col1, selector_col2 = (
                            st.columns(2)
                        )

                        with selector_col1:

                            baseline_experiment_id = (
                                st.selectbox(
                                    "Baseline Experiment",
                                    options=option_ids,
                                    index=baseline_index,
                                    format_func=lambda x:
                                        option_labels.get(
                                            x,
                                            x,
                                        ),
                                    key=(
                                        "rnd_baseline_experiment"
                                    ),
                                )
                            )

                        with selector_col2:

                            candidate_experiment_id = (
                                st.selectbox(
                                    "Candidate / Current Experiment",
                                    options=option_ids,
                                    index=candidate_index,
                                    format_func=lambda x:
                                        option_labels.get(
                                            x,
                                            x,
                                        ),
                                    key=(
                                        "rnd_candidate_experiment"
                                    ),
                                )
                            )

                        if (
                            baseline_experiment_id
                            == candidate_experiment_id
                        ):

                            st.warning(
                                "Baseline and candidate are the same "
                                "experiment. Select different experiments "
                                "for a meaningful comparison."
                            )

                        factor_rows = query_duckdb(
                            f"""
                            SELECT
                                experiment_id,
                                factor_group,
                                feature_id,
                                weight,
                                direction,
                                enabled
                            FROM analytics.main.experiment_run_factors
                            WHERE experiment_id IN (
                                '{baseline_experiment_id.replace("'", "''")}',
                                '{candidate_experiment_id.replace("'", "''")}'
                            )
                            """
                        )

                        if factor_rows.empty:

                            st.info(
                                "No factor configuration records "
                                "were found for the selected experiments."
                            )

                        else:

                            factor_labels = {
                                "return_20d":
                                    "Return 20D",
                                "return_60d":
                                    "Return 60D",
                                "return_252d":
                                    "Return 252D",
                                "price_vs_ma_20d":
                                    "Price vs MA 20D",
                                "price_vs_ma_60d":
                                    "Price vs MA 60D",
                                "price_vs_ma_252d":
                                    "Price vs MA 252D",
                                "volatility_20d":
                                    "Volatility 20D",
                                "volatility_60d":
                                    "Volatility 60D",
                                "volatility_252d":
                                    "Volatility 252D",
                                "drawdown_252d":
                                    "Drawdown 252D",
                            }

                            group_order = [
                                "MOMENTUM",
                                "TREND",
                                "RISK",
                                "DRAWDOWN",
                            ]

                            feature_order = {
                                "MOMENTUM": [
                                    "return_20d",
                                    "return_60d",
                                    "return_252d",
                                ],
                                "TREND": [
                                    "price_vs_ma_20d",
                                    "price_vs_ma_60d",
                                    "price_vs_ma_252d",
                                ],
                                "RISK": [
                                    "volatility_20d",
                                    "volatility_60d",
                                    "volatility_252d",
                                ],
                                "DRAWDOWN": [
                                    "drawdown_252d",
                                ],
                            }

                            baseline_factors = (
                                factor_rows[
                                    factor_rows[
                                        "experiment_id"
                                    ]
                                    == baseline_experiment_id
                                ]
                                .set_index(
                                    "feature_id"
                                )
                            )

                            candidate_factors = (
                                factor_rows[
                                    factor_rows[
                                        "experiment_id"
                                    ]
                                    == candidate_experiment_id
                                ]
                                .set_index(
                                    "feature_id"
                                )
                            )

                            # ----------------------------------------
                            # Group-level comparison
                            # ----------------------------------------

                            st.markdown(
                                "### ⚖️ Factor Group Weights"
                            )

                            group_rows = []

                            for group in group_order:

                                baseline_group = (
                                    factor_rows[
                                        (
                                            factor_rows[
                                                "experiment_id"
                                            ]
                                            == baseline_experiment_id
                                        )
                                        & (
                                            factor_rows[
                                                "factor_group"
                                            ]
                                            == group
                                        )
                                    ]
                                )

                                candidate_group = (
                                    factor_rows[
                                        (
                                            factor_rows[
                                                "experiment_id"
                                            ]
                                            == candidate_experiment_id
                                        )
                                        & (
                                            factor_rows[
                                                "factor_group"
                                            ]
                                            == group
                                        )
                                    ]
                                )

                                baseline_weight = (
                                    safe_float(
                                        baseline_group[
                                            "weight"
                                        ].sum()
                                    )
                                )

                                candidate_weight = (
                                    safe_float(
                                        candidate_group[
                                            "weight"
                                        ].sum()
                                    )
                                )

                                group_rows.append(
                                    {
                                        "Factor Group":
                                            group.title(),
                                        "Baseline":
                                            baseline_weight,
                                        "Candidate":
                                            candidate_weight,
                                        "Δ":
                                            (
                                                candidate_weight
                                                - baseline_weight
                                            ),
                                    }
                                )

                            group_display = (
                                pd.DataFrame(
                                    group_rows
                                )
                            )

                            st.dataframe(
                                group_display.style.format(
                                    {
                                        "Baseline":
                                            "{:.2%}",
                                        "Candidate":
                                            "{:.2%}",
                                        "Δ":
                                            "{:+.2%}",
                                    }
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )

                            # ----------------------------------------
                            # Individual factor comparison
                            # ----------------------------------------

                            st.markdown(
                                "### 🔬 Individual Factor Details"
                            )

                            factor_comparison_rows = []

                            for group in group_order:

                                for feature_id in (
                                    feature_order[group]
                                ):

                                    factor_baseline_row = (
                                        baseline_factors.loc[
                                            feature_id
                                        ]
                                        if feature_id
                                        in baseline_factors.index
                                        else None
                                    )

                                    factor_candidate_row = (
                                        candidate_factors.loc[
                                            feature_id
                                        ]
                                        if feature_id
                                        in candidate_factors.index
                                        else None
                                    )

                                    baseline_weight = (
                                        safe_float(
                                            factor_baseline_row[
                                                "weight"
                                            ]
                                        )
                                        if factor_baseline_row
                                        is not None
                                        else 0.0
                                    )

                                    candidate_weight = (
                                        safe_float(
                                            factor_candidate_row[
                                                "weight"
                                            ]
                                        )
                                        if factor_candidate_row
                                        is not None
                                        else 0.0
                                    )

                                    baseline_enabled = (
                                        bool(
                                            factor_baseline_row[
                                                "enabled"
                                            ]
                                        )
                                        if factor_baseline_row
                                        is not None
                                        else False
                                    )

                                    candidate_enabled = (
                                        bool(
                                            factor_candidate_row[
                                                "enabled"
                                            ]
                                        )
                                        if factor_candidate_row
                                        is not None
                                        else False
                                    )

                                    direction = (
                                        int(
                                            factor_baseline_row[
                                                "direction"
                                            ]
                                        )
                                        if factor_baseline_row
                                        is not None
                                        else (
                                            int(
                                                factor_candidate_row[
                                                    "direction"
                                                ]
                                            )
                                            if factor_candidate_row
                                            is not None
                                            else 1
                                        )
                                    )

                                    factor_comparison_rows.append(
                                        {
                                            "Factor Group":
                                                group.title(),
                                            "Factor / Parameter":
                                                factor_labels.get(
                                                    feature_id,
                                                    feature_id,
                                                ),
                                            "Direction":
                                                (
                                                    "Positive"
                                                    if direction == 1
                                                    else "Negative"
                                                ),
                                            "Baseline Enabled":
                                                (
                                                    "✓"
                                                    if baseline_enabled
                                                    else "✗"
                                                ),
                                            "Baseline Weight":
                                                baseline_weight,
                                            "Candidate Enabled":
                                                (
                                                    "✓"
                                                    if candidate_enabled
                                                    else "✗"
                                                ),
                                            "Candidate Weight":
                                                candidate_weight,
                                            "Δ Weight":
                                                (
                                                    candidate_weight
                                                    - baseline_weight
                                                ),
                                        }
                                    )

                            factor_comparison = (
                                pd.DataFrame(
                                    factor_comparison_rows
                                )
                            )

                            st.dataframe(
                                factor_comparison.style.format(
                                    {
                                        "Baseline Weight":
                                            "{:.2%}",
                                        "Candidate Weight":
                                            "{:.2%}",
                                        "Δ Weight":
                                            "{:+.2%}",
                                    }
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )

                # ========================================================
                # EXPERIMENT DETAILS
                # ========================================================

                with review_details:

                    st.caption(
                        "Technical metadata and configuration details "
                        "for the selected experiment."
                    )

                    experiment_options = (
                        evaluations[
                            [
                                "experiment_id",
                                "experiment_name",
                            ]
                        ]
                        .drop_duplicates()
                    )

                    selected_experiment = (
                        st.selectbox(
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
                    )

                    selected_eval = (
                        evaluations[
                            evaluations[
                                "experiment_id"
                            ]
                            == selected_experiment
                        ].iloc[0]
                    )

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

                    if not experiment.empty:

                        exp = experiment.iloc[0]

                        col1, col2, col3, col4 = (
                            st.columns(4)
                        )

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
                            f"{safe_float(selected_eval['net_cagr_pct']):.2f}%",
                        )

                        col4.metric(
                            "Sharpe",
                            f"{safe_float(selected_eval['net_sharpe']):.2f}",
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
                                    exp[
                                        "top_n"
                                    ],
                                    (
                                        f"{safe_float(exp['transaction_cost_rate']) * 100:.3f}%"
                                    ),
                                    exp[
                                        "status"
                                    ],
                                    exp[
                                        "created_at"
                                    ],
                                    selected_eval[
                                        "start_date"
                                    ],
                                    selected_eval[
                                        "end_date"
                                    ],
                                    safe_int(
                                        selected_eval[
                                            "weeks"
                                        ]
                                    ),
                                ],
                            }
                        )

                        st.dataframe(
                            metadata,
                            use_container_width=True,
                            hide_index=True,
                        )

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
                            "No standard baseline is available "
                            "in this batch."
                        )

                    st.info(
                        "R&D results are for research and human review only. "
                        "Promoting an experiment to production remains a "
                        "deliberate configuration-management decision."
                    )

    except Exception as e:

        st.error(
            f"Unable to load R&D experiments: {e}"
        )

        st.exception(e)


# ============================================================
# CONFIGURATION MANAGER
# ============================================================

with tab_config:

    st.header(
        "Configuration Manager"
    )

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

            st.info(
                "No strategy configurations available."
            )

        else:

            selected_config = st.selectbox(
                "Configuration",
                configurations[
                    "configuration_id"
                ].tolist(),
                format_func=lambda x: (
                    f"Config {int(x)} — "
                    f"{configurations.loc[configurations['configuration_id'] == x, 'strategy_name'].iloc[0]}"
                ),
                key=(
                    "config_manager_configuration"
                ),
            )

            config = configurations[
                configurations[
                    "configuration_id"
                ]
                == selected_config
            ].iloc[0]

            st.subheader(
                "Configuration Overview"
            )

            col1, col2, col3, col4 = (
                st.columns(4)
            )

            col1.metric(
                "Configuration ID",
                int(
                    config[
                        "configuration_id"
                    ]
                ),
            )

            col2.metric(
                "Version",
                int(
                    config[
                        "configuration_version"
                    ]
                ),
            )

            col3.metric(
                "Top N",
                int(
                    config["top_n"]
                ),
            )

            col4.metric(
                "Status",
                str(
                    config["status"]
                ),
            )

            st.write(
                f"**Strategy:** "
                f"{config['strategy_id']}"
            )

            st.write(
                f"**Name:** "
                f"{config['strategy_name']}"
            )

            st.write(
                f"**Type:** "
                f"{config['configuration_type']}"
            )

            st.subheader(
                "Factor Group Weights"
            )

            group_weights_df = query_df(
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
                    "configuration_id":
                        selected_config,
                },
            )

            group_display = (
                group_weights_df.copy()
            )

            group_display[
                "group_weight"
            ] = (
                group_display[
                    "group_weight"
                ] * 100
            ).round(2)

            group_display = group_display.rename(
                columns={
                    "factor_group_id":
                        "Factor Group",
                    "factor_group_name":
                        "Name",
                    "group_weight":
                        "Weight %",
                    "enabled":
                        "Enabled",
                }
            )

            st.dataframe(
                group_display,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader(
                "Factor Weights"
            )

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
                    "configuration_id":
                        selected_config,
                },
            )

            factor_display = (
                factors.copy()
            )

            factor_display[
                "feature_weight"
            ] = (
                factor_display[
                    "feature_weight"
                ] * 100
            ).round(2)

            factor_display = factor_display.rename(
                columns={
                    "factor_group_id":
                        "Factor Group",
                    "feature_id":
                        "Feature",
                    "feature_weight":
                        "Weight %",
                    "direction":
                        "Direction",
                    "enabled":
                        "Enabled",
                }
            )

            st.dataframe(
                factor_display,
                use_container_width=True,
                hide_index=True,
            )

            st.subheader(
                "Portfolio & Signal Settings"
            )

            settings = {
                "Position Weight":
                    f"{safe_float(config['position_weight']) * 100:.2f}%",
                "Transaction Cost Rate":
                    f"{safe_float(config['transaction_cost_rate']) * 100:.3f}%",
                "Signal Frequency":
                    config["signal_frequency"],
                "Entry Rule":
                    config["entry_rule"],
                "Rebalance Rule":
                    config["rebalance_rule"],
            }

            st.table(
                {
                    "Setting":
                        list(settings.keys()),
                    "Value":
                        list(settings.values()),
                }
            )

    except Exception as e:

        st.error(
            f"Unable to load configuration manager: {e}"
        )
