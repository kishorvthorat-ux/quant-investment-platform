import importlib
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


import config_lifecycle as config_ops

config_ops = importlib.reload(config_ops)

PROTECTED_CONFIGURATION_IDS = (
    config_ops.PROTECTED_CONFIGURATION_IDS
)
PROTECTED_STRATEGY_IDS = (
    config_ops.PROTECTED_STRATEGY_IDS
)
build_promotion_snapshot = (
    config_ops.build_promotion_snapshot
)
delete_configuration = (
    config_ops.delete_configuration
)
freeze_configuration = config_ops.freeze_configuration
promote_rnd_configuration = (
    config_ops.promote_rnd_configuration
)
retire_configuration = config_ops.retire_configuration
run_production_v2_dbt = config_ops.run_production_v2_dbt
validate_draft_configuration = (
    config_ops.validate_draft_configuration
)

from research.run_experiment import (
    run_custom_experiment,
    DEFAULT_GROUP_WEIGHTS,
    DEFAULT_FACTOR_WEIGHTS,
    FACTOR_GROUPS,
)

from research.experiment_maintenance import (
    delete_experiment_runs,
    ensure_label_columns,
    format_run_label,
    get_protected_baseline_id,
    list_completed_runs,
    rename_run_display_name,
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


def format_prod_config_label(
    configuration_id,
    strategy_name=None,
    top_n=None,
    status=None,
):
    label = f"Config {int(configuration_id)}"

    if strategy_name:
        label += f" — {strategy_name}"

    extras = []

    if top_n is not None and pd.notna(top_n):
        extras.append(f"Top {int(top_n)}")

    if status is not None and pd.notna(status):
        extras.append(str(status))

    if extras:
        label += f" ({', '.join(extras)})"

    return label


def rnd_mix_from_session_state():
    group_weights = {}

    for group in DEFAULT_GROUP_WEIGHTS:
        group_weights[group] = float(
            st.session_state.get(
                f"rnd_group_{group}",
                DEFAULT_GROUP_WEIGHTS[group],
            )
        )

    factor_weights = {}
    factor_enabled = {}

    for factor in DEFAULT_FACTOR_WEIGHTS:
        enabled = bool(
            st.session_state.get(
                f"rnd_enabled_{factor}",
                True,
            )
        )
        factor_enabled[factor] = enabled

        if enabled:
            factor_weights[factor] = float(
                st.session_state.get(
                    f"rnd_factor_{factor}",
                    DEFAULT_FACTOR_WEIGHTS[factor],
                )
            )
        else:
            factor_weights[factor] = 0.0

    transaction_cost_pct = float(
        st.session_state.get(
            "rnd_transaction_cost",
            0.20,
        )
    )

    return {
        "group_weights": group_weights,
        "factor_weights": factor_weights,
        "factor_enabled": factor_enabled,
        "top_n": int(
            st.session_state.get("rnd_top_n", 2)
        ),
        "transaction_cost_rate": transaction_cost_pct / 100.0,
        "source_label": "Current R&D workbench mix",
    }


def rnd_mix_from_saved_config(config):
    group_weights = {
        group: float(
            config.get("group_weights", {}).get(
                group,
                DEFAULT_GROUP_WEIGHTS[group],
            )
        )
        for group in DEFAULT_GROUP_WEIGHTS
    }

    factor_enabled = {}
    factor_weights = {}

    saved_enabled = config.get("factor_enabled", {})
    saved_weights = config.get("factor_weights", {})

    for factor in DEFAULT_FACTOR_WEIGHTS:
        enabled = bool(saved_enabled.get(factor, True))
        factor_enabled[factor] = enabled
        factor_weights[factor] = (
            float(saved_weights.get(factor, DEFAULT_FACTOR_WEIGHTS[factor]))
            if enabled
            else 0.0
        )

    transaction_cost_pct = float(
        config.get("transaction_cost_pct", 0.20)
    )

    return {
        "group_weights": group_weights,
        "factor_weights": factor_weights,
        "factor_enabled": factor_enabled,
        "top_n": int(config.get("top_n", 2)),
        "transaction_cost_rate": transaction_cost_pct / 100.0,
        "source_label": f"Saved R&D mix: {config.get('name')}",
    }


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

    if existing_index is not None:
        previous = configs[existing_index]
        for key in (
            "production_configuration_id",
            "production_strategy_id",
            "production_status",
        ):
            if previous.get(key) is not None:
                configuration[key] = previous[key]

    if existing_index is None:

        configs.append(configuration)

    else:

        configs[existing_index] = configuration

    write_saved_rnd_configs(configs)

    return configuration


def link_saved_rnd_to_production(name, result):
    configs = load_saved_rnd_configs()
    saved = find_saved_rnd_config(configs, name)

    if saved is None:
        return

    saved["production_configuration_id"] = int(
        result["configuration_id"]
    )
    saved["production_strategy_id"] = result["strategy_id"]
    saved["production_status"] = result["status"]
    saved["updated_at"] = datetime.now().isoformat(
        timespec="seconds"
    )
    write_saved_rnd_configs(configs)


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


def reload_experiment_runner():
    import research.run_experiment as run_experiment_mod

    return importlib.reload(run_experiment_mod)


def build_factor_impact_table(
    evaluations,
    baseline_row,
    selected_row,
):
    sensitivity = evaluations[
        evaluations["experiment_type"] == "WEIGHT_SENSITIVITY"
    ].copy()

    if sensitivity.empty:
        return sensitivity

    group_labels = {
        "MOMENTUM": "Momentum",
        "TREND": "Trend",
        "RISK": "Risk",
        "DRAWDOWN": "Drawdown",
    }

    def shock_label(value):
        try:
            delta = float(value)
        except (TypeError, ValueError):
            return str(value)

        if abs(delta - 0.01) < 1e-9:
            return "+1%"

        return f"{delta:+.2f}"

    baseline_cagr = (
        safe_float(baseline_row["net_cagr_pct"])
        if baseline_row is not None
        else None
    )
    baseline_sharpe = (
        safe_float(baseline_row["net_sharpe"])
        if baseline_row is not None
        else None
    )
    baseline_dd = (
        safe_float(baseline_row["net_max_drawdown_pct"])
        if baseline_row is not None
        else None
    )

    selected_cagr = (
        safe_float(selected_row["net_cagr_pct"])
        if selected_row is not None
        else None
    )
    selected_sharpe = (
        safe_float(selected_row["net_sharpe"])
        if selected_row is not None
        else None
    )
    selected_dd = (
        safe_float(selected_row["net_max_drawdown_pct"])
        if selected_row is not None
        else None
    )

    rows = []

    for _, row in sensitivity.iterrows():
        cagr = safe_float(row["net_cagr_pct"])
        sharpe = safe_float(row["net_sharpe"])
        drawdown = safe_float(row["net_max_drawdown_pct"])

        rows.append(
            {
                "Factor group": group_labels.get(
                    str(row.get("parameter_name") or ""),
                    str(row.get("parameter_name") or ""),
                ),
                "Shock": shock_label(row.get("parameter_value")),
                "_delta": safe_float(row.get("parameter_value")),
                "Net CAGR %": round(cagr, 2),
                "vs Baseline CAGR": (
                    round(cagr - baseline_cagr, 2)
                    if baseline_cagr is not None
                    else None
                ),
                "vs Selected CAGR": (
                    round(cagr - selected_cagr, 2)
                    if selected_cagr is not None
                    else None
                ),
                "Sharpe": round(sharpe, 2),
                "vs Baseline Sharpe": (
                    round(sharpe - baseline_sharpe, 2)
                    if baseline_sharpe is not None
                    else None
                ),
                "vs Selected Sharpe": (
                    round(sharpe - selected_sharpe, 2)
                    if selected_sharpe is not None
                    else None
                ),
                "Max DD %": round(drawdown, 2),
                "vs Baseline DD": (
                    round(drawdown - baseline_dd, 2)
                    if baseline_dd is not None
                    else None
                ),
                "vs Selected DD": (
                    round(drawdown - selected_dd, 2)
                    if selected_dd is not None
                    else None
                ),
            }
        )

    table = pd.DataFrame(rows)

    if not table.empty:
        table = table.sort_values(
            ["Factor group", "_delta"],
            ignore_index=True,
        ).drop(columns=["_delta"])

    return table


def render_factor_impact_highlights(impact_table):
    if impact_table is None or impact_table.empty:
        return

    work = impact_table.copy()
    work["cagr_vs_selected"] = pd.to_numeric(
        work["vs Selected CAGR"],
        errors="coerce",
    )
    work["sharpe_vs_selected"] = pd.to_numeric(
        work["vs Selected Sharpe"],
        errors="coerce",
    )
    work["dd_vs_selected"] = pd.to_numeric(
        work["vs Selected DD"],
        errors="coerce",
    )

    work = work.dropna(subset=["cagr_vs_selected"])

    if work.empty:
        return

    helpful = work[
        (work["cagr_vs_selected"] > 0.15)
        & (work["sharpe_vs_selected"].fillna(0) >= -0.02)
    ].sort_values(
        ["cagr_vs_selected", "sharpe_vs_selected"],
        ascending=False,
    )

    harmful = work[
        (work["cagr_vs_selected"] < -0.15)
        | (
            (work["cagr_vs_selected"] < 0)
            & (work["sharpe_vs_selected"].fillna(0) < -0.05)
        )
    ].sort_values(
        ["cagr_vs_selected", "sharpe_vs_selected"],
        ascending=True,
    )

    st.subheader(
        "Outcomes vs selected config"
    )

    st.caption(
        "Shocks that raise CAGR without a clear Sharpe loss are "
        "treated as positive. Worse CAGR or a clear Sharpe drop "
        "is treated as negative. Drawdown deltas are shown for context "
        "(positive DD delta means a shallower loss)."
    )

    positive_col, negative_col = st.columns(2)

    with positive_col:

        st.markdown(
            "**Positive**"
        )

        top_positive = helpful.head(4)

        if top_positive.empty:

            st.info(
                "No shock clearly beat the selected mix."
            )

        else:

            for _, row in top_positive.iterrows():

                dd_text = ""
                dd_value = row["dd_vs_selected"]

                if pd.notna(dd_value):
                    dd_text = f", DD {dd_value:+.2f} pp"

                st.success(
                    f"{row['Factor group']} {row['Shock']}: "
                    f"CAGR {row['cagr_vs_selected']:+.2f} pp, "
                    f"Sharpe {safe_float(row['sharpe_vs_selected']):+.2f}"
                    f"{dd_text}"
                )

    with negative_col:

        st.markdown(
            "**Negative**"
        )

        top_negative = harmful.head(4)

        if top_negative.empty:

            st.info(
                "No shock clearly hurt the selected mix."
            )

        else:

            for _, row in top_negative.iterrows():

                dd_text = ""
                dd_value = row["dd_vs_selected"]

                if pd.notna(dd_value):
                    dd_text = f", DD {dd_value:+.2f} pp"

                st.error(
                    f"{row['Factor group']} {row['Shock']}: "
                    f"CAGR {row['cagr_vs_selected']:+.2f} pp, "
                    f"Sharpe {safe_float(row['sharpe_vs_selected']):+.2f}"
                    f"{dd_text}"
                )


def style_signed_dataframe(frame, signed_columns):
    if frame is None or frame.empty:
        return frame

    formatters = {}

    for column in frame.columns:
        if column in ("Factor group", "Shock", "Top N", "Note"):
            continue

        if column in signed_columns:
            formatters[column] = "{:+.2f}"
        else:
            formatters[column] = "{:.2f}"

    styler = frame.style.format(formatters)

    def colorize(series):
        styles = []

        for value in series:
            if pd.isna(value):
                styles.append("")
            elif float(value) > 0:
                styles.append(
                    "color: #067a32; font-weight: 600"
                )
            elif float(value) < 0:
                styles.append(
                    "color: #b42318; font-weight: 600"
                )
            else:
                styles.append("")

        return styles

    for column in signed_columns:
        if column in frame.columns:
            styler = styler.apply(
                colorize,
                subset=[column],
            )

    return styler


def render_factor_group_impact_tables(impact_table):
    if impact_table is None or impact_table.empty:
        return

    st.subheader(
        "Factor group analysis"
    )

    st.caption(
        "Each card is one factor group. Rows are weight shocks "
        "around the selected mix. Δ is versus the unshocked mix."
    )

    group_order = [
        "Momentum",
        "Trend",
        "Risk",
        "Drawdown",
    ]

    present = [
        group
        for group in group_order
        if (impact_table["Factor group"] == group).any()
    ]

    extra = [
        group
        for group in impact_table["Factor group"].dropna().unique()
        if group not in present
    ]

    present.extend(extra)

    show_columns = [
        "Shock",
        "Net CAGR %",
        "vs Selected CAGR",
        "Sharpe",
        "vs Selected Sharpe",
        "Max DD %",
        "vs Selected DD",
    ]

    rename = {
        "Net CAGR %": "CAGR %",
        "vs Selected CAGR": "Δ CAGR",
        "vs Selected Sharpe": "Δ Sharpe",
        "vs Selected DD": "Δ DD",
    }

    signed = ["Δ CAGR", "Δ Sharpe", "Δ DD"]

    for index in range(0, len(present), 2):

        columns = st.columns(2)

        for column, group in zip(
            columns,
            present[index:index + 2],
        ):

            subset = impact_table[
                impact_table["Factor group"] == group
            ].copy()

            available = [
                name
                for name in show_columns
                if name in subset.columns
            ]

            display = subset[available].rename(
                columns=rename
            )

            with column:

                st.markdown(
                    f"**{group}**"
                )

                st.dataframe(
                    style_signed_dataframe(
                        display,
                        signed,
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


def build_top_n_impact_table(
    evaluations,
    baseline_row,
    selected_row,
):
    if evaluations is None or evaluations.empty:
        return pd.DataFrame()

    selected_cagr = (
        safe_float(selected_row["net_cagr_pct"])
        if selected_row is not None
        else None
    )
    selected_sharpe = (
        safe_float(selected_row["net_sharpe"])
        if selected_row is not None
        else None
    )
    selected_dd = (
        safe_float(selected_row["net_max_drawdown_pct"])
        if selected_row is not None
        else None
    )

    selected_top_n = None

    if selected_row is not None:
        try:
            selected_top_n = int(selected_row.get("top_n"))
        except (TypeError, ValueError):
            selected_top_n = None

    def metric_row(source, top_n, note):
        cagr = safe_float(source["net_cagr_pct"])
        sharpe = safe_float(source["net_sharpe"])
        drawdown = safe_float(source["net_max_drawdown_pct"])

        return {
            "Top N": int(top_n),
            "Note": note,
            "Net CAGR %": round(cagr, 2),
            "Δ CAGR vs selected": (
                round(cagr - selected_cagr, 2)
                if selected_cagr is not None
                else None
            ),
            "Sharpe": round(sharpe, 2),
            "Δ Sharpe vs selected": (
                round(sharpe - selected_sharpe, 2)
                if selected_sharpe is not None
                else None
            ),
            "Max DD %": round(drawdown, 2),
            "Δ DD vs selected": (
                round(drawdown - selected_dd, 2)
                if selected_dd is not None
                else None
            ),
        }

    rows = []

    if selected_row is not None and selected_top_n is not None:
        rows.append(
            metric_row(
                selected_row,
                selected_top_n,
                "Selected",
            )
        )

    sensitivity = evaluations[
        evaluations["experiment_type"] == "TOP_N_SENSITIVITY"
    ]

    for _, row in sensitivity.iterrows():
        try:
            top_n = int(
                row.get("parameter_value")
                if pd.notna(row.get("parameter_value"))
                else row.get("top_n")
            )
        except (TypeError, ValueError):
            continue

        note = ""

        if selected_top_n is not None and top_n == selected_top_n:
            note = "Selected"

        rows.append(metric_row(row, top_n, note))

    table = pd.DataFrame(rows)

    if table.empty:
        return table

    return (
        table.sort_values(
            ["Top N", "Note"],
            ascending=[True, False],
            ignore_index=True,
        )
        .drop_duplicates(
            subset=["Top N"],
            keep="first",
        )
    )


def render_top_n_impact(top_n_table):
    st.subheader(
        "Top-N impact"
    )

    st.caption(
        "Same selected mix, equal-weight Top 2 / 3 / 4 / 5. "
        "The selected Top N is marked. Re-run factor sensitivity "
        "if this table is empty."
    )

    if top_n_table is None or top_n_table.empty:

        st.info(
            "No Top-N sensitivity rows in this batch yet. "
            "Run factor sensitivity again to add Top 2, 3, 4, and 5."
        )

        return

    display = top_n_table.rename(
        columns={
            "Net CAGR %": "CAGR %",
            "Δ CAGR vs selected": "Δ CAGR",
            "Δ Sharpe vs selected": "Δ Sharpe",
            "Δ DD vs selected": "Δ DD",
        }
    )

    st.dataframe(
        style_signed_dataframe(
            display,
            ["Δ CAGR", "Δ Sharpe", "Δ DD"],
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_yearly_factor_impact(yearly_df, selected_id):
    st.subheader(
        "Year-wise factor impact"
    )

    st.caption(
        "Calendar-year net return minus the selected mix in "
        "that year. Positive means the group shock beat the "
        "selected mix in that year."
    )

    if yearly_df is None or yearly_df.empty:

        st.info(
            "No yearly results for this sensitivity batch. "
            "Re-run factor sensitivity after evaluation."
        )

        return

    selected_yearly = yearly_df[
        yearly_df["experiment_id"] == selected_id
    ]

    selected_by_year = {
        int(row["year"]): safe_float(row["return_pct"])
        for _, row in selected_yearly.iterrows()
    }

    group_labels = {
        "MOMENTUM": "Momentum",
        "TREND": "Trend",
        "RISK": "Risk",
        "DRAWDOWN": "Drawdown",
    }

    def shock_label(value):
        try:
            delta = float(value)
        except (TypeError, ValueError):
            return str(value)

        if abs(delta - 0.01) < 1e-9:
            return "+1%"

        return f"{delta:+.2f}"

    shocks = yearly_df[
        yearly_df["experiment_type"] == "WEIGHT_SENSITIVITY"
    ].copy()

    if shocks.empty:

        st.info(
            "This batch has yearly rows but no factor-group shocks."
        )

        return

    records = []

    for _, row in shocks.iterrows():
        year = int(row["year"])
        ret = safe_float(row["return_pct"])
        selected_ret = selected_by_year.get(year)

        records.append(
            {
                "Factor group": group_labels.get(
                    str(row.get("parameter_name") or ""),
                    str(row.get("parameter_name") or ""),
                ),
                "Shock": shock_label(row.get("parameter_value")),
                "_delta": safe_float(row.get("parameter_value")),
                "year": year,
                "Δ vs selected": (
                    round(ret - selected_ret, 2)
                    if selected_ret is not None
                    else None
                ),
            }
        )

    work = pd.DataFrame(records)

    if work.empty or work["Δ vs selected"].isna().all():

        st.info(
            "Could not compare yearly shocks with the selected mix."
        )

        return

    pivot = work.pivot_table(
        index=["Factor group", "Shock", "_delta"],
        columns="year",
        values="Δ vs selected",
        aggfunc="first",
    ).reset_index().sort_values(
        ["Factor group", "_delta"],
        ignore_index=True,
    ).drop(columns=["_delta"])

    year_columns = [
        column
        for column in pivot.columns
        if column not in ("Factor group", "Shock")
    ]

    st.dataframe(
        style_signed_dataframe(
            pivot,
            year_columns,
        ),
        use_container_width=True,
        hide_index=True,
    )

    if year_columns:

        st.caption(
            "Largest positive and negative group shock in each year."
        )

        for start in range(0, len(year_columns), 4):

            chunk = year_columns[start:start + 4]
            highlight_cols = st.columns(len(chunk))

            for column, year in zip(highlight_cols, chunk):

                year_view = work[
                    work["year"].astype(int) == int(year)
                ].dropna(
                    subset=["Δ vs selected"]
                )

                with column:

                    st.markdown(
                        f"**{year}**"
                    )

                    if year_view.empty:

                        st.caption("No data")
                        continue

                    best = year_view.loc[
                        year_view["Δ vs selected"].idxmax()
                    ]
                    worst = year_view.loc[
                        year_view["Δ vs selected"].idxmin()
                    ]

                    st.success(
                        f"{best['Factor group']} {best['Shock']}: "
                        f"{best['Δ vs selected']:+.2f} pp"
                    )
                    st.error(
                        f"{worst['Factor group']} {worst['Shock']}: "
                        f"{worst['Δ vs selected']:+.2f} pp"
                    )

    top_n_yearly = yearly_df[
        yearly_df["experiment_type"] == "TOP_N_SENSITIVITY"
    ].copy()

    if top_n_yearly.empty:
        return

    with st.expander(
        "Year-wise Top-N",
        expanded=False,
    ):

        top_records = []

        for _, row in top_n_yearly.iterrows():
            try:
                top_n = int(
                    row.get("parameter_value")
                    if pd.notna(row.get("parameter_value"))
                    else row.get("top_n")
                )
            except (TypeError, ValueError):
                continue

            year = int(row["year"])
            ret = safe_float(row["return_pct"])
            selected_ret = selected_by_year.get(year)

            top_records.append(
                {
                    "Top N": top_n,
                    "year": year,
                    "Δ vs selected": (
                        round(ret - selected_ret, 2)
                        if selected_ret is not None
                        else None
                    ),
                }
            )

        selected_runs = yearly_df[
            yearly_df["experiment_id"] == selected_id
        ]
        selected_top_n = None

        if (
            not selected_runs.empty
            and "top_n" in selected_runs.columns
        ):
            try:
                selected_top_n = int(
                    selected_runs.iloc[0]["top_n"]
                )
            except (TypeError, ValueError):
                selected_top_n = None

        if selected_top_n is not None:
            for year in selected_by_year:
                top_records.append(
                    {
                        "Top N": selected_top_n,
                        "year": year,
                        "Δ vs selected": 0.0,
                    }
                )

        top_work = pd.DataFrame(top_records)

        if top_work.empty:
            st.info("No yearly Top-N comparison.")
            return

        top_pivot = top_work.pivot_table(
            index="Top N",
            columns="year",
            values="Δ vs selected",
            aggfunc="first",
        ).reset_index().sort_values("Top N")

        top_year_columns = [
            column
            for column in top_pivot.columns
            if column != "Top N"
        ]

        st.dataframe(
            style_signed_dataframe(
                top_pivot,
                top_year_columns,
            ),
            use_container_width=True,
            hide_index=True,
        )


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
        candidate.get("display_name")
        or candidate["experiment_name"]
    )

    if baseline is not None:

        baseline_name = str(
            baseline.get("display_name")
            or baseline["experiment_name"]
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
        "Ann. turnover",
        f"{safe_float(candidate['turnover_pct']):.1f}%",
        help="Annualized one-way turnover. Research currently rebalances every day, so this is higher than the weekly production path.",
    )

    col2.metric(
        "Cost drag",
        f"{safe_float(candidate['transaction_cost_pct']):.2f}%",
        help="Cumulative return lost to transaction costs over the full sample.",
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
                    f"ann. turnover {turnover_delta:+.1f} pp"
                )

            if cost_delta > 0:

                qualifiers.append(
                    f"cost drag {cost_delta:+.2f} pp"
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
                SELECT DISTINCT
                    s.configuration_id,
                    c.strategy_name,
                    c.top_n,
                    c.status
                FROM analytics.weekly_signals_v2 s
                LEFT JOIN analytics.strategy_config_version c
                  ON c.configuration_id = s.configuration_id
                WHERE s.signal_date = %(signal_date)s
                  AND s.strategy_id = %(strategy_id)s
                ORDER BY s.configuration_id
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
                format_func=lambda x: format_prod_config_label(
                    x,
                    configurations.loc[
                        configurations["configuration_id"] == x,
                        "strategy_name",
                    ].iloc[0],
                    configurations.loc[
                        configurations["configuration_id"] == x,
                        "top_n",
                    ].iloc[0],
                    configurations.loc[
                        configurations["configuration_id"] == x,
                        "status",
                    ].iloc[0],
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
                p.configuration_id,
                p.strategy_id,
                c.strategy_name,
                c.top_n,
                c.status,
                p.start_date,
                p.end_date,
                p.trading_days,
                p.gross_return_pct,
                p.gross_cagr_pct,
                p.gross_volatility_pct,
                p.gross_sharpe,
                p.gross_max_drawdown_pct,
                p.net_return_pct,
                p.net_cagr_pct,
                p.net_volatility_pct,
                p.net_sharpe,
                p.net_max_drawdown_pct,
                p.annualized_turnover_pct,
                p.transaction_cost_pct,
                p.net_win_rate_pct,
                p.best_day_pct,
                p.worst_day_pct
            FROM analytics.portfolio_performance_metrics_v2 p
            LEFT JOIN analytics.strategy_config_version c
              ON c.configuration_id = p.configuration_id
            ORDER BY p.strategy_id, p.configuration_id
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

            perf["Configuration"] = [
                format_prod_config_label(
                    row["configuration_id"],
                    row.get("strategy_name"),
                    row.get("top_n"),
                    row.get("status"),
                )
                for _, row in perf.iterrows()
            ]

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
        "Adjust a mix, optionally save it, pick a baseline, then run. "
        "Research runs stay in DuckDB. To put a mix in the production "
        "config table, use Configuration Manager."
    )

    saved_configs = load_saved_rnd_configs()

    saved_config_names = [
        str(config.get("name", "Unnamed"))
        for config in saved_configs
    ]

    new_config_label = "Current / new configuration"

    pending_delete = st.session_state.pop(
        "rnd_pending_delete",
        None,
    )

    if pending_delete:

        try:

            delete_rnd_configuration(
                pending_delete
            )

            st.session_state[
                "rnd_config_name"
            ] = ""

            st.session_state[
                "rnd_saved_config_selector"
            ] = new_config_label

            st.session_state.pop(
                "rnd_selected_saved_config",
                None,
            )

            st.session_state[
                "rnd_action_message"
            ] = f"Deleted: {pending_delete}"

        except Exception as e:

            st.session_state[
                "rnd_action_error"
            ] = f"Unable to delete configuration: {e}"

        saved_configs = load_saved_rnd_configs()

        saved_config_names = [
            str(config.get("name", "Unnamed"))
            for config in saved_configs
        ]

    pending_rename = st.session_state.pop(
        "rnd_pending_rename",
        None,
    )

    if pending_rename:

        old_name = str(
            pending_rename.get("old", "")
        ).strip()

        new_name = str(
            pending_rename.get("new", "")
        ).strip()

        try:

            rename_rnd_configuration(
                old_name,
                new_name,
            )

            st.session_state[
                "rnd_config_name"
            ] = new_name

            st.session_state[
                "rnd_saved_config_selector"
            ] = new_name

            st.session_state[
                "rnd_selected_saved_config"
            ] = new_name

            st.session_state[
                "rnd_action_message"
            ] = f"Renamed to: {new_name}"

        except Exception as e:

            st.session_state[
                "rnd_action_error"
            ] = f"Unable to rename configuration: {e}"

        saved_configs = load_saved_rnd_configs()

        saved_config_names = [
            str(config.get("name", "Unnamed"))
            for config in saved_configs
        ]

    pending_load = st.session_state.pop(
        "rnd_pending_load",
        None,
    )

    if pending_load:

        pending_config = find_saved_rnd_config(
            saved_configs,
            pending_load,
        )

        if pending_config is not None:

            apply_saved_rnd_config_to_session(
                pending_config
            )

            st.session_state[
                "rnd_selected_saved_config"
            ] = pending_load

            st.session_state[
                "rnd_saved_config_selector"
            ] = pending_load

            st.session_state[
                "rnd_action_message"
            ] = f"Loaded: {pending_load}"

        else:

            st.session_state[
                "rnd_action_error"
            ] = f"Could not load saved mix: {pending_load}"

    pending_run_rename = st.session_state.pop(
        "rnd_pending_run_rename",
        None,
    )

    if pending_run_rename:

        try:

            rename_run_display_name(
                pending_run_rename["experiment_id"],
                pending_run_rename["display_name"],
            )

            st.session_state[
                "rnd_action_message"
            ] = (
                "Renamed experiment to: "
                + pending_run_rename["display_name"]
            )

        except Exception as e:

            st.session_state[
                "rnd_action_error"
            ] = f"Unable to rename experiment: {e}"

    pending_run_cleanup = st.session_state.pop(
        "rnd_pending_run_cleanup",
        None,
    )

    if pending_run_cleanup:

        try:

            deleted_count = delete_experiment_runs(
                pending_run_cleanup
            )

            protected_id = get_protected_baseline_id()

            selected_baseline = st.session_state.get(
                "rnd_selected_baseline"
            )

            if (
                selected_baseline
                in pending_run_cleanup
            ):

                st.session_state[
                    "rnd_selected_baseline"
                ] = protected_id

            st.session_state[
                "rnd_action_message"
            ] = (
                f"Removed {deleted_count} research run"
                f"{'s' if deleted_count != 1 else ''}."
            )

        except Exception as e:

            st.session_state[
                "rnd_action_error"
            ] = f"Unable to clean research runs: {e}"

    ensure_label_columns()


    group_labels = {
        "MOMENTUM": "Momentum",
        "TREND": "Trend",
        "RISK": "Risk",
        "DRAWDOWN": "Drawdown",
    }

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

    # ========================================================
    # 1. ADJUST CONFIGURATION
    # ========================================================

    st.subheader(
        "1. Adjust configuration"
    )

    st.caption(
        "Set group weights, factor enablement, Top-N, and cost. "
        "Weights are fractions (0.40 = 40%). The research engine "
        "normalizes them before scoring."
    )

    action_message = st.session_state.pop(
        "rnd_action_message",
        None,
    )

    action_error = st.session_state.pop(
        "rnd_action_error",
        None,
    )

    if action_message:

        st.success(
            action_message
        )

    if action_error:

        st.error(
            action_error
        )

    with st.expander(
        "Factor group weights",
        expanded=False,
    ):

        group_cols = st.columns(4)

        group_weights = {}

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
                help=(
                    "Share of the composite score for this group. "
                    "Set to 0 to exclude the group."
                ),
            )

        group_total = sum(
            group_weights.values()
        )

        if group_total <= 0:

            st.error(
                "At least one factor group must have a weight greater than zero."
            )

        else:

            st.caption(
                "Current mix: "
                + " · ".join(
                    f"{group_labels[group]} "
                    f"{100.0 * weight / group_total:.0f}%"
                    for group, weight in group_weights.items()
                    if weight > 0
                )
                + f"  |  raw total {group_total:.2f}"
            )

    with st.expander(
        "Individual factor weights",
        expanded=False,
    ):

        factor_weights = {}
        factor_enabled = {}

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
                    "On",
                    value=True,
                    key=f"rnd_enabled_{factor}",
                    help=f"Include {factor_labels[factor]} in scoring.",
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
                    col.caption("Off")

    with st.expander(
        "Portfolio settings",
        expanded=False,
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
            help="Equal weight 1/N across the selected names.",
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
                help="Applied to turnover. 0.20 means 20 basis points.",
            )
        )

        transaction_cost_rate = (
            transaction_cost_pct / 100.0
        )

        st.caption(
            f"Each selected name gets "
            f"{100.0 / float(top_n):.1f}% weight. "
            f"Cost rate used in the backtest: "
            f"{transaction_cost_rate:.4f}."
        )

    # ========================================================
    # 2. SAVE / LOAD
    # ========================================================

    st.divider()

    st.subheader(
        "2. Save this configuration"
    )

    st.caption(
        "Optional. Saving keeps this mix for R&D reloads and lists it "
        "in Configuration Manager. Production Postgres tables are "
        "written only when you move it to DRAFT or VALIDATED there."
    )

    saved_selection_options = [
        new_config_label
    ] + saved_config_names

    load_col, save_name_col = st.columns(
        [1, 1]
    )

    with load_col:

        selected_saved_config = st.selectbox(
            "Load a saved mix",
            saved_selection_options,
            key="rnd_saved_config_selector",
            help="Choose a saved mix, then Load to replace the sliders above.",
        )

        load_saved = st.button(
            "Load",
            use_container_width=True,
            key="rnd_load_saved",
        )

    with save_name_col:

        st.text_input(
            "Name to save as",
            key="rnd_config_name",
            placeholder="e.g. Trend heavy v1",
            help="Used for Save and Rename.",
        )

        save_configuration_button = st.button(
            "Save",
            type="primary",
            use_container_width=True,
            key="rnd_save_configuration",
        )

    rename_col, delete_col, _ = st.columns(
        [1, 1, 2]
    )

    with rename_col:

        rename_configuration_button = st.button(
            "Rename selected",
            use_container_width=True,
            key="rnd_rename_configuration",
        )

    with delete_col:

        delete_configuration_button = st.button(
            "Delete selected",
            use_container_width=True,
            key="rnd_delete_configuration",
        )

    if load_saved:

        if selected_saved_config == new_config_label:

            st.warning(
                "Choose a saved mix first, then click Load."
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

                st.session_state[
                    "rnd_pending_load"
                ] = selected_saved_config

                st.rerun()

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
            == new_config_label
        ):

            st.warning(
                "Choose a saved mix to rename."
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

                st.session_state[
                    "rnd_pending_rename"
                ] = {
                    "old": selected_saved_config,
                    "new": new_name,
                }

                st.rerun()

    # ========================================================
    # DELETE CONFIGURATION
    # ========================================================

    if delete_configuration_button:

        if (
            selected_saved_config
            == new_config_label
        ):

            st.warning(
                "Choose a saved mix to delete."
            )

        else:

            st.session_state[
                "rnd_pending_delete"
            ] = selected_saved_config

            st.rerun()

    # ========================================================
    # R&D BASELINE SELECTION
    # ========================================================

    st.divider()

    st.subheader(
        "3. Comparison baseline"
    )

    st.caption(
        "Choose the mix you want to beat. Names are editable. "
        "The protected main baseline cannot be deleted."
    )

    baseline_options_df = list_completed_runs()

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

        baseline_ids = (
            baseline_options_df[
                "experiment_id"
            ].tolist()
        )

        baseline_labels = {
            row["experiment_id"]: format_run_label(row)
            for _, row in baseline_options_df.iterrows()
        }

        protected_id = get_protected_baseline_id()

        if (
            protected_id
            and protected_id in baseline_ids
        ):

            default_baseline_id = protected_id

        else:

            default_baseline_id = baseline_ids[0]

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
                "Compare against",
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
                "Top N",
                safe_int(
                    baseline_display_row["top_n"]
                ),
            )

            baseline_info_col2.metric(
                "Cost",
                f"{safe_float(baseline_display_row['transaction_cost_rate']):.2%}",
            )

            baseline_info_col3.metric(
                "Type",
                str(
                    baseline_display_row[
                        "experiment_type"
                    ]
                ).replace("_", " ").title(),
            )

            rename_col, rename_button_col = st.columns(
                [3, 1]
            )

            current_display = str(
                baseline_display_row.get(
                    "display_name"
                )
                or ""
            ).strip()

            display_name_key = (
                "rnd_baseline_display_name_"
                + str(selected_baseline_experiment_id)
            )

            if display_name_key not in st.session_state:
                st.session_state[display_name_key] = (
                    current_display
                )

            with rename_col:

                st.text_input(
                    "Display name",
                    key=display_name_key,
                    help=(
                        "This name is only for the R&D UI. "
                        "Internal experiment IDs stay unchanged."
                    ),
                )

            with rename_button_col:

                st.write("")
                rename_run_clicked = st.button(
                    "Save name",
                    use_container_width=True,
                    key="rnd_rename_run_display",
                )

            if rename_run_clicked:

                new_display_name = str(
                    st.session_state.get(
                        display_name_key,
                        "",
                    )
                ).strip()

                if not new_display_name:

                    st.warning(
                        "Enter a display name before saving."
                    )

                else:

                    st.session_state[
                        "rnd_pending_run_rename"
                    ] = {
                        "experiment_id": (
                            selected_baseline_experiment_id
                        ),
                        "display_name": new_display_name,
                    }

                    st.rerun()

            with st.expander(
                "Clean previous runs",
                expanded=False,
            ):

                st.caption(
                    "Removes DuckDB research runs and their scores, "
                    "portfolios, and evaluations. Production Postgres "
                    "and the protected main baseline are not touched."
                )

                deletable = baseline_options_df[
                    ~baseline_options_df[
                        "is_protected"
                    ].fillna(False)
                ].copy()

                if deletable.empty:

                    st.info(
                        "There are no extra runs to remove."
                    )

                else:

                    deletable["label"] = (
                        deletable.apply(
                            format_run_label,
                            axis=1,
                        )
                    )

                    cleanup_ids = (
                        deletable[
                            "experiment_id"
                        ].tolist()
                    )

                    cleanup_labels = dict(
                        zip(
                            deletable["experiment_id"],
                            deletable["label"],
                        )
                    )

                    selected_cleanup_ids = st.multiselect(
                        "Runs to remove",
                        options=cleanup_ids,
                        format_func=lambda x:
                            cleanup_labels.get(x, x),
                        key="rnd_cleanup_ids",
                    )

                    confirm_cleanup = st.checkbox(
                        "I understand these research runs cannot be restored",
                        key="rnd_confirm_cleanup",
                    )

                    clean_selected, clean_all = st.columns(2)

                    with clean_selected:

                        clean_selected_clicked = st.button(
                            "Remove selected",
                            use_container_width=True,
                            key="rnd_clean_selected",
                        )

                    with clean_all:

                        clean_all_clicked = st.button(
                            "Remove all except main baseline",
                            use_container_width=True,
                            key="rnd_clean_all",
                        )

                    if clean_selected_clicked:

                        if not selected_cleanup_ids:

                            st.warning(
                                "Select at least one run to remove."
                            )

                        elif not confirm_cleanup:

                            st.warning(
                                "Tick the confirmation box first."
                            )

                        else:

                            st.session_state[
                                "rnd_pending_run_cleanup"
                            ] = list(
                                selected_cleanup_ids
                            )

                            st.rerun()

                    if clean_all_clicked:

                        if not confirm_cleanup:

                            st.warning(
                                "Tick the confirmation box first."
                            )

                        else:

                            st.session_state[
                                "rnd_pending_run_cleanup"
                            ] = cleanup_ids

                            st.rerun()

    # ========================================================
    # RUN EXPERIMENT
    # ========================================================

    run_col, sensitivity_col = st.columns(2)

    with run_col:

        run_rnd = st.button(
            "Run R&D experiment",
            type="primary",
            use_container_width=True,
            key="run_custom_rnd",
        )

    with sensitivity_col:

        run_sensitivity = st.button(
            "Run factor sensitivity",
            use_container_width=True,
            key="run_factor_sensitivity",
            help=(
                "Shock each factor-group weight by "
                "−0.50, −0.25, +0.25, +0.50, and +1%, "
                "and also run Top 2, 3, 4, and 5. "
                "Compare with the baseline and this selected config."
            ),
        )

    st.caption(
        "Factor sensitivity keeps the selected mix as the centre, "
        "then tilts Momentum, Trend, Risk, and Drawdown by "
        "−0.50, −0.25, +0.25, +0.50, and +1 percentage point. "
        "It also reruns the same mix at Top 2, 3, 4, and 5. "
        "Weights are renormalized. Results appear in the "
        "Factor impact tab. This can take several minutes."
    )

    if st.session_state.pop(
        "rnd_pending_sensitivity",
        None,
    ):

        run_sensitivity = True

    if run_rnd or run_sensitivity:

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

                saved_run_name = (
                    str(
                        st.session_state.get(
                            "rnd_config_name",
                            "",
                        )
                    ).strip()
                    or None
                )

                spinner_label = (
                    "Running factor-group sensitivity "
                    "(−0.50, −0.25, +0.25, +0.50, +1%) "
                    "and evaluating results..."
                    if run_sensitivity
                    else "Running R&D experiment and evaluating results..."
                )

                with st.spinner(spinner_label):

                    runner = reload_experiment_runner()

                    run_kwargs = {
                        "group_weights": group_weights,
                        "factor_weights": factor_weights,
                        "top_n": int(top_n),
                        "transaction_cost_rate": (
                            transaction_cost_rate
                        ),
                        "baseline_experiment_id": (
                            selected_baseline_experiment_id
                        ),
                    }

                    if run_sensitivity:
                        try:
                            experiment_id = (
                                runner.run_factor_sensitivity_experiment(
                                    **run_kwargs,
                                    display_name=saved_run_name,
                                )
                            )
                        except TypeError:
                            experiment_id = (
                                runner.run_factor_sensitivity_experiment(
                                    **run_kwargs
                                )
                            )
                    else:
                        experiment_id = (
                            runner.run_custom_experiment(
                                **run_kwargs
                            )
                        )

                    if saved_run_name:

                        rename_run_display_name(
                            experiment_id,
                            saved_run_name,
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
        "Creating a production snapshot is done in Configuration Manager."
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
                    COALESCE(
                        r.display_name,
                        e.experiment_name
                    ) AS display_name,
                    r.parameter_name,
                    r.parameter_value,
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

                custom_rows = evaluations[
                    evaluations["experiment_type"]
                    == "CUSTOM_RND"
                ]

                last_experiment_id = (
                    st.session_state.get(
                        "rnd_last_experiment"
                    )
                )

                if (
                    last_experiment_id
                    and last_experiment_id
                    in evaluations["experiment_id"].values
                ):

                    candidate_row = evaluations[
                        evaluations["experiment_id"]
                        == last_experiment_id
                    ].iloc[0]

                elif not custom_rows.empty:

                    candidate_row = custom_rows.iloc[0]

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

                review_performance, review_why, review_impact, review_details = (
                    st.tabs(
                        [
                            "📈 Performance",
                            "🔬 Why It Changed",
                            "Factor impact",
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
                            r.parameter_name,
                            r.parameter_value,
                            r.top_n,
                            r.transaction_cost_rate,
                            r.status,
                            r.created_at,
                            r.display_name,
                            COALESCE(r.is_protected, FALSE) AS is_protected
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
                            "display_name_ui"
                        ] = comparison_experiments.apply(
                            format_run_label,
                            axis=1,
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
                                    "is_protected"
                                ].fillna(False)
                            ]
                        )

                        if baseline_candidates.empty:

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
                                    "display_name_ui"
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
                # FACTOR IMPACT
                # ========================================================

                with review_impact:

                    st.caption(
                        "Group-weight shocks (−0.50, −0.25, +0.25, +0.50, "
                        "+1%) plus Top 2 / 3 / 4 / 5 on the selected mix. "
                        "Compare each result with the unshocked config "
                        "and the comparison baseline."
                    )

                    sensitivity_evals = query_duckdb(
                        """
                        WITH latest_sensitivity AS (
                            SELECT split_part(
                                experiment_id,
                                '_',
                                1
                            ) AS batch_id
                            FROM analytics.main.experiment_runs
                            WHERE experiment_type = 'WEIGHT_SENSITIVITY'
                              AND status = 'COMPLETED'
                            ORDER BY created_at DESC
                            LIMIT 1
                        )
                        SELECT
                            e.experiment_id,
                            e.experiment_type,
                            e.experiment_name,
                            COALESCE(
                                r.display_name,
                                e.experiment_name
                            ) AS display_name,
                            r.parameter_name,
                            r.parameter_value,
                            r.top_n,
                            e.net_cagr_pct,
                            e.net_sharpe,
                            e.net_max_drawdown_pct
                        FROM analytics.main.experiment_evaluations e
                        JOIN analytics.main.experiment_runs r
                          ON e.experiment_id = r.experiment_id
                        JOIN latest_sensitivity ls
                          ON split_part(
                                e.experiment_id,
                                '_',
                                1
                             ) = ls.batch_id
                        """
                    )

                    if sensitivity_evals.empty:
                        impact_source = evaluations
                    else:
                        impact_source = sensitivity_evals

                    impact_baseline = None
                    impact_selected = None

                    if not impact_source.empty:

                        baseline_hits = impact_source[
                            impact_source["experiment_name"]
                            == "FACTOR_ABLATION_BASELINE_None"
                        ]
                        selected_hits = impact_source[
                            impact_source["experiment_type"]
                            == "CUSTOM_RND"
                        ]

                        if not baseline_hits.empty:
                            impact_baseline = baseline_hits.iloc[0]
                        elif baseline_row is not None:
                            impact_baseline = baseline_row

                        if not selected_hits.empty:
                            impact_selected = selected_hits.iloc[0]
                        elif candidate_row is not None:
                            impact_selected = candidate_row

                    impact_table = build_factor_impact_table(
                        impact_source,
                        impact_baseline,
                        impact_selected,
                    )

                    if impact_table.empty:

                        st.info(
                            "No factor-sensitivity results yet. "
                            "This is a separate run from a normal R&D "
                            "experiment. It tilts each factor group, "
                            "runs Top 2–5, and can take several minutes."
                        )

                        if st.button(
                            "Run factor sensitivity for this mix",
                            key="rnd_run_sens_tab",
                        ):

                            st.session_state[
                                "rnd_pending_sensitivity"
                            ] = True

                            st.rerun()

                    else:

                        render_factor_impact_highlights(
                            impact_table
                        )

                        render_factor_group_impact_tables(
                            impact_table
                        )

                        with st.expander(
                            "Full group-shock table vs baseline",
                            expanded=False,
                        ):

                            st.dataframe(
                                style_signed_dataframe(
                                    impact_table,
                                    [
                                        "vs Baseline CAGR",
                                        "vs Selected CAGR",
                                        "vs Baseline Sharpe",
                                        "vs Selected Sharpe",
                                        "vs Baseline DD",
                                        "vs Selected DD",
                                    ],
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )

                            st.caption(
                                "vs Selected is versus the unshocked mix "
                                "in this batch. vs Baseline is versus the "
                                "comparison baseline. Positive CAGR/Sharpe "
                                "is better; less-negative max drawdown is "
                                "better."
                            )

                        top_n_table = build_top_n_impact_table(
                            impact_source,
                            impact_baseline,
                            impact_selected,
                        )

                        render_top_n_impact(top_n_table)

                        selected_id = None

                        if impact_selected is not None:
                            selected_id = impact_selected.get(
                                "experiment_id"
                            )

                        yearly_impact = query_duckdb(
                            """
                            WITH latest_sensitivity AS (
                                SELECT split_part(
                                    experiment_id,
                                    '_',
                                    1
                                ) AS batch_id
                                FROM analytics.main.experiment_runs
                                WHERE experiment_type
                                    = 'WEIGHT_SENSITIVITY'
                                  AND status = 'COMPLETED'
                                ORDER BY created_at DESC
                                LIMIT 1
                            )
                            SELECT
                                y.experiment_id,
                                y.year,
                                y.return_pct,
                                r.experiment_type,
                                r.parameter_name,
                                r.parameter_value,
                                r.top_n
                            FROM analytics.main.experiment_yearly_results y
                            JOIN analytics.main.experiment_runs r
                              ON y.experiment_id = r.experiment_id
                            JOIN latest_sensitivity ls
                              ON split_part(
                                    y.experiment_id,
                                    '_',
                                    1
                                 ) = ls.batch_id
                            ORDER BY y.year, r.experiment_type
                            """
                        )

                        render_yearly_factor_impact(
                            yearly_impact,
                            selected_id,
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
                        "To copy a finalized mix into the production config "
                        "table, use Configuration Manager."
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
        "Saved R&D mixes appear here. Move one to DRAFT or VALIDATED "
        "to copy it into Postgres strategy_config, "
        "strategy_factor_groups, and strategy_factors. Configs 1 and 2 "
        "cannot be changed. Production dbt is optional and does not "
        "touch DuckDB R&D."
    )

    pending_select = st.session_state.pop(
        "config_pending_select",
        None,
    )

    if pending_select is not None:
        st.session_state[
            "config_manager_item"
        ] = str(pending_select)

    action_message = st.session_state.pop(
        "config_action_message",
        None,
    )

    action_error = st.session_state.pop(
        "config_action_error",
        None,
    )

    if action_message:
        st.success(action_message)

    if action_error:
        st.error(action_error)

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

        saved_rnd_items = load_saved_rnd_configs()
        pg_ids = set()

        if not configurations.empty:
            pg_ids = {
                int(value)
                for value in configurations["configuration_id"]
            }

        option_keys = []
        option_labels = {}

        if not configurations.empty:
            for _, row in configurations.iterrows():
                key = f"pg:{int(row['configuration_id'])}"
                option_keys.append(key)
                option_labels[key] = format_prod_config_label(
                    row["configuration_id"],
                    row.get("strategy_name"),
                    row.get("top_n"),
                    row.get("status"),
                )

        for saved in saved_rnd_items:
            linked_id = saved.get("production_configuration_id")
            if linked_id is not None:
                try:
                    if int(linked_id) in pg_ids:
                        continue
                except (TypeError, ValueError):
                    pass

            saved_name = str(saved.get("name", "Unnamed"))
            key = f"rnd:{saved_name}"
            option_keys.append(key)
            option_labels[key] = (
                f"R&D saved — {saved_name} (not in Postgres)"
            )

        if not option_keys:

            st.info(
                "No production snapshots or saved R&D mixes yet. "
                "Save a mix in the R&D workbench first."
            )

        else:

            current_item = st.session_state.get(
                "config_manager_item"
            )

            if current_item not in option_keys:
                st.session_state["config_manager_item"] = (
                    option_keys[0]
                )

            selected_key = st.selectbox(
                "Configuration",
                option_keys,
                format_func=lambda key: option_labels.get(key, key),
                key="config_manager_item",
            )

            if str(selected_key).startswith("rnd:"):

                rnd_name = str(selected_key)[4:]
                saved_mix = find_saved_rnd_config(
                    saved_rnd_items,
                    rnd_name,
                )

                st.subheader(
                    "Saved R&D mix"
                )

                st.caption(
                    "This mix is stored from the R&D workbench. "
                    "Moving it to DRAFT or VALIDATED copies weights "
                    "into Postgres strategy_config, "
                    "strategy_factor_groups, and strategy_factors, "
                    "and creates a version snapshot. It does not "
                    "change M_RD_504010_V2."
                )

                if saved_mix is None:

                    st.error(
                        "That saved R&D mix could not be loaded."
                    )

                else:

                    promote_mix = rnd_mix_from_saved_config(
                        saved_mix
                    )

                    try:
                        snapshot = build_promotion_snapshot(
                            promote_mix["group_weights"],
                            promote_mix["factor_weights"],
                            promote_mix["factor_enabled"],
                            promote_mix["top_n"],
                            promote_mix["transaction_cost_rate"],
                            rnd_name,
                        )
                    except Exception as preview_error:
                        snapshot = None
                        st.warning(str(preview_error))

                    if snapshot is not None:

                        preview_cols = st.columns(3)
                        preview_cols[0].metric(
                            "Top N",
                            snapshot["top_n"],
                        )
                        preview_cols[1].metric(
                            "Position weight",
                            f"{float(snapshot['position_weight']) * 100:.2f}%",
                        )
                        preview_cols[2].metric(
                            "Transaction cost",
                            f"{float(snapshot['transaction_cost_rate']) * 100:.3f}%",
                        )

                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Factor group": row["factor_group_name"],
                                        "Weight %": round(
                                            float(row["group_weight"]) * 100,
                                            2,
                                        ),
                                        "Enabled": row["enabled"],
                                    }
                                    for row in snapshot["groups"]
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Factor group": row["factor_group_id"].title(),
                                        "Feature": row["feature_id"],
                                        "Weight %": round(
                                            float(row["feature_weight"]) * 100,
                                            2,
                                        ),
                                        "Direction": row["direction"],
                                        "Enabled": row["enabled"],
                                    }
                                    for row in snapshot["factors"]
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )

                    rnd_confirm = st.checkbox(
                        "Copy this R&D mix into new Postgres strategy "
                        "tables. Configs 1 and 2 will not change.",
                        key="config_rnd_publish_confirm",
                    )

                    draft_col, validated_col = st.columns(2)

                    draft_clicked = draft_col.button(
                        "Move to DRAFT",
                        use_container_width=True,
                        key="config_rnd_to_draft",
                    )
                    validated_clicked = validated_col.button(
                        "Move to VALIDATED",
                        type="primary",
                        use_container_width=True,
                        key="config_rnd_to_validated",
                    )

                    if draft_clicked or validated_clicked:

                        if not rnd_confirm:

                            st.warning(
                                "Tick the confirmation box first."
                            )

                        elif snapshot is None:

                            st.error(
                                "This mix cannot be published."
                            )

                        else:

                            target_status = (
                                "VALIDATED"
                                if validated_clicked
                                else "DRAFT"
                            )

                            try:

                                result = promote_rnd_configuration(
                                    promote_mix["group_weights"],
                                    promote_mix["factor_weights"],
                                    promote_mix["factor_enabled"],
                                    promote_mix["top_n"],
                                    promote_mix["transaction_cost_rate"],
                                    rnd_name,
                                    target_status=target_status,
                                )
                                link_saved_rnd_to_production(
                                    rnd_name,
                                    result,
                                )
                                st.session_state[
                                    "config_pending_select"
                                ] = (
                                    f"pg:{result['configuration_id']}"
                                )
                                st.session_state[
                                    "config_action_message"
                                ] = (
                                    f"Created strategy "
                                    f"{result['strategy_id']} "
                                    f"(config {result['configuration_id']}, "
                                    f"{result['status']}) from R&D mix "
                                    f"'{rnd_name}'. "
                                    "Run production V2 dbt if status is "
                                    "VALIDATED."
                                )
                                st.rerun()

                            except Exception as publish_error:

                                st.session_state[
                                    "config_action_error"
                                ] = str(publish_error)
                                st.rerun()

            else:

                selected_config = int(
                    str(selected_key).split(":", 1)[1]
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

                selected_id = int(config["configuration_id"])
                selected_status = str(config["status"])
                selected_strategy_id = str(config["strategy_id"])
                is_protected = (
                    selected_id in PROTECTED_CONFIGURATION_IDS
                )
                needs_own_strategy = (
                    selected_status == "DRAFT"
                    or (
                        selected_status == "VALIDATED"
                        and selected_strategy_id in PROTECTED_STRATEGY_IDS
                    )
                )

                st.subheader(
                    "Lifecycle"
                )

                if is_protected:

                    st.info(
                        f"Config {selected_id} is protected. Validate, "
                        "freeze, retire, and delete are disabled."
                    )

                else:

                    st.caption(
                        "Validate makes this snapshot a new production "
                        "strategy (not another version of M_RD_504010_V2). "
                        "Freeze locks that strategy snapshot. Retire drops "
                        "it from scoring. Delete removes the snapshot and, "
                        "if nothing else uses the strategy, the strategy row."
                    )

                    lifecycle_confirm = st.checkbox(
                        "I confirm this lifecycle change. Configs 1 and 2 "
                        "will not be modified.",
                        key="config_lifecycle_confirm",
                    )

                    validate_col, freeze_col, retire_col, delete_col = (
                        st.columns(4)
                    )

                    validate_clicked = validate_col.button(
                        "Validate as strategy",
                        disabled=not needs_own_strategy,
                        use_container_width=True,
                        key="config_validate",
                    )
                    freeze_clicked = freeze_col.button(
                        "Freeze",
                        disabled=(
                            selected_status != "VALIDATED"
                            or selected_strategy_id in PROTECTED_STRATEGY_IDS
                        ),
                        use_container_width=True,
                        key="config_freeze",
                    )
                    retire_clicked = retire_col.button(
                        "Retire",
                        disabled=selected_status == "RETIRED",
                        use_container_width=True,
                        key="config_retire",
                    )
                    delete_clicked = delete_col.button(
                        "Delete",
                        use_container_width=True,
                        key="config_delete",
                    )

                    if (
                        validate_clicked
                        or freeze_clicked
                        or retire_clicked
                        or delete_clicked
                    ):

                        if not lifecycle_confirm:

                            st.warning(
                                "Tick the confirmation box first."
                            )

                        else:

                            try:

                                if validate_clicked:
                                    result = (
                                        validate_draft_configuration(
                                            selected_id
                                        )
                                    )
                                    message = (
                                        "Created strategy "
                                        f"{result['strategy_id']} from "
                                        f"config {result['configuration_id']}. "
                                        "Run production V2 dbt to score it. "
                                        "It will appear as its own strategy "
                                        "in Signal Review."
                                    )

                                elif freeze_clicked:
                                    result = freeze_configuration(
                                        selected_id
                                    )
                                    message = (
                                        f"Froze config "
                                        f"{result['configuration_id']}. "
                                        "It stays in production scoring "
                                        "and cannot be edited here."
                                    )

                                elif retire_clicked:
                                    result = retire_configuration(
                                        selected_id
                                    )
                                    message = (
                                        f"Retired config "
                                        f"{result['configuration_id']}. "
                                        "The next production dbt run will "
                                        "stop scoring it."
                                    )

                                else:
                                    result = delete_configuration(
                                        selected_id
                                    )
                                    remaining = configurations[
                                        configurations[
                                            "configuration_id"
                                        ]
                                        != selected_id
                                    ]
                                    if not remaining.empty:
                                        st.session_state[
                                            "config_pending_select"
                                        ] = int(
                                            remaining.iloc[0][
                                                "configuration_id"
                                            ]
                                        )
                                    message = (
                                        f"Deleted config "
                                        f"{result['configuration_id']} "
                                        f"({result['strategy_name']})."
                                    )

                                st.session_state[
                                    "config_action_message"
                                ] = message
                                st.rerun()

                            except Exception as lifecycle_error:

                                st.session_state[
                                    "config_action_error"
                                ] = str(lifecycle_error)
                                st.rerun()

                st.subheader(
                    "Run production V2"
                )

                st.caption(
                    "Rebuilds Postgres V2 analytics "
                    "(rankings, weights, signals, performance) for every "
                    "VALIDATED and FROZEN config. DRAFT snapshots will not "
                    "appear in Signal Review or Strategy Performance. "
                    "Does not run DuckDB R&D and does not change snapshots."
                )

                dbt_confirm = st.checkbox(
                    "I want to run production dbt for V2 now.",
                    key="config_dbt_confirm",
                )

                dbt_clicked = st.button(
                    "Run production dbt for V2",
                    key="config_run_dbt",
                )

                if dbt_clicked:

                    if not dbt_confirm:

                        st.warning(
                            "Tick the production dbt confirmation first."
                        )

                    else:

                        with st.spinner(
                            "Running production V2 dbt build..."
                        ):

                            try:

                                dbt_log = run_production_v2_dbt()

                                st.session_state[
                                    "config_action_message"
                                ] = (
                                    "Production V2 dbt build completed. "
                                    "Use Signal Review and Strategy "
                                    "Performance to select scored configs."
                                )
                                st.session_state[
                                    "config_dbt_log"
                                ] = dbt_log
                                st.rerun()

                            except Exception as dbt_error:

                                st.session_state[
                                    "config_action_error"
                                ] = str(dbt_error)
                                st.rerun()

                dbt_log = st.session_state.get("config_dbt_log")

                if dbt_log:

                    with st.expander(
                        "Last production dbt log",
                        expanded=False,
                    ):
                        st.code(dbt_log, language="text")

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
