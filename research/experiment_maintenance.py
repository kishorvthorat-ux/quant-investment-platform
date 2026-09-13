from __future__ import annotations

from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "duckdb" / "analytics.duckdb"

MAIN_BASELINE_INTERNAL_NAME = "FACTOR_ABLATION_BASELINE_None"
MAIN_BASELINE_DEFAULT_LABEL = "Main baseline (MTRD default)"

GROUP_LABELS = {
    "MOMENTUM": "Momentum",
    "TREND": "Trend",
    "RISK": "Risk",
    "DRAWDOWN": "Drawdown",
}

RUN_TABLES = (
    "experiment_scores",
    "experiment_portfolios",
    "experiment_run_factors",
    "experiment_evaluations",
    "experiment_yearly_results",
    "experiment_results",
    "experiment_factors",
    "experiment_factor_groups",
    "experiments",
    "experiment_runs",
)


def get_connection():
    return duckdb.connect(str(DB_PATH))


def default_display_name(
    experiment_name,
    experiment_type=None,
    parameter_name=None,
    parameter_value=None,
    top_n=None,
    protected=False,
):
    name = str(experiment_name or "")

    if protected:
        return MAIN_BASELINE_DEFAULT_LABEL

    if name == MAIN_BASELINE_INTERNAL_NAME:
        return "Baseline copy for this run"

    if experiment_type == "FACTOR_ABLATION" and str(parameter_name).startswith("REMOVE_"):
        group = str(parameter_name).replace("REMOVE_", "")
        return f"Ablation: no {GROUP_LABELS.get(group, group.title())}"

    if experiment_type == "SUBFACTOR_ABLATION" and str(parameter_name).startswith("REMOVE_"):
        feature = (
            str(parameter_name)
            .replace("REMOVE_", "")
            .replace("_", " ")
            .title()
        )
        return f"Ablation: no {feature}"

    if experiment_type == "CUSTOM_RND":
        return "Custom mix"

    if experiment_type == "TOP_N_SENSITIVITY":
        try:
            return f"Top {int(parameter_value)}"
        except (TypeError, ValueError):
            return "Top-N experiment"

    if experiment_type == "COST_SENSITIVITY":
        try:
            return f"Transaction cost {float(parameter_value):.2%}"
        except (TypeError, ValueError):
            return "Cost experiment"

    if experiment_type == "WEIGHT_SENSITIVITY":
        group = GROUP_LABELS.get(
            str(parameter_name),
            str(parameter_name).title(),
        )
        return f"{group} weight {parameter_value}"

    return name.replace("_", " ").title()


def format_run_label(row) -> str:
    display = str(row.get("display_name") or "").strip()

    if not display:
        display = default_display_name(
            row.get("experiment_name"),
            row.get("experiment_type"),
            row.get("parameter_name"),
            row.get("parameter_value"),
            row.get("top_n"),
            bool(row.get("is_protected")),
        )

    created = row.get("created_at")
    created_label = ""

    if created is not None:
        created_label = str(created)[:10]

    top_n = row.get("top_n")
    top_label = f"Top {int(top_n)}" if top_n is not None else ""

    suffix_parts = [part for part in (top_label, created_label) if part]
    suffix = " · ".join(suffix_parts)

    if bool(row.get("is_protected")):
        prefix = "Protected · "
    else:
        prefix = ""

    if suffix:
        return f"{prefix}{display} · {suffix}"

    return f"{prefix}{display}"


def ensure_label_columns(conn=None):
    close = False

    if conn is None:
        conn = get_connection()
        close = True

    try:
        conn.execute(
            """
            ALTER TABLE analytics.main.experiment_runs
            ADD COLUMN IF NOT EXISTS display_name VARCHAR
            """
        )
        conn.execute(
            """
            ALTER TABLE analytics.main.experiment_runs
            ADD COLUMN IF NOT EXISTS is_protected BOOLEAN DEFAULT FALSE
            """
        )
        seed_experiment_labels(conn)
    finally:
        if close:
            conn.close()


def seed_experiment_labels(conn):
    rows = conn.execute(
        """
        SELECT
            experiment_id,
            experiment_name,
            experiment_type,
            parameter_name,
            parameter_value,
            top_n,
            status,
            display_name,
            COALESCE(is_protected, FALSE) AS is_protected,
            created_at
        FROM analytics.main.experiment_runs
        ORDER BY created_at
        """
    ).fetchdf()

    if rows.empty:
        return

    completed_baselines = rows[
        (rows["experiment_name"] == MAIN_BASELINE_INTERNAL_NAME)
        & (rows["status"].astype(str).str.upper() == "COMPLETED")
    ]

    protected_rows = rows[rows["is_protected"].fillna(False)]
    protected_is_completed = False

    if not protected_rows.empty:
        protected_is_completed = (
            str(protected_rows.iloc[0]["status"]).upper() == "COMPLETED"
        )

    if (not protected_is_completed) and (not completed_baselines.empty):
        main_id = completed_baselines.iloc[0]["experiment_id"]

        conn.execute(
            """
            UPDATE analytics.main.experiment_runs
            SET is_protected = FALSE
            """
        )

        conn.execute(
            """
            UPDATE analytics.main.experiment_runs
            SET is_protected = TRUE,
                display_name = ?
            WHERE experiment_id = ?
            """,
            [MAIN_BASELINE_DEFAULT_LABEL, main_id],
        )

        rows["is_protected"] = False
        rows.loc[
            rows["experiment_id"] == main_id,
            "is_protected",
        ] = True
        rows.loc[
            rows["experiment_id"] == main_id,
            "display_name",
        ] = MAIN_BASELINE_DEFAULT_LABEL

    for _, row in rows.iterrows():
        current = str(row.get("display_name") or "").strip()

        if current:
            continue

        label = default_display_name(
            row["experiment_name"],
            row["experiment_type"],
            row["parameter_name"],
            row["parameter_value"],
            row["top_n"],
            bool(row["is_protected"]),
        )

        conn.execute(
            """
            UPDATE analytics.main.experiment_runs
            SET display_name = ?
            WHERE experiment_id = ?
            """,
            [label, row["experiment_id"]],
        )


def get_protected_baseline_id(conn=None):
    close = False

    if conn is None:
        conn = get_connection()
        close = True

    try:
        ensure_label_columns(conn)

        row = conn.execute(
            """
            SELECT experiment_id
            FROM analytics.main.experiment_runs
            WHERE COALESCE(is_protected, FALSE) = TRUE
              AND status = 'COMPLETED'
            ORDER BY created_at
            LIMIT 1
            """
        ).fetchone()

        if row:
            return row[0]

        return None
    finally:
        if close:
            conn.close()


def rename_run_display_name(experiment_id: str, display_name: str):
    display_name = str(display_name).strip()

    if not display_name:
        raise ValueError("Display name cannot be empty.")

    conn = get_connection()

    try:
        ensure_label_columns(conn)

        exists = conn.execute(
            """
            SELECT experiment_id
            FROM analytics.main.experiment_runs
            WHERE experiment_id = ?
            """,
            [experiment_id],
        ).fetchone()

        if exists is None:
            raise ValueError(
                "The selected experiment no longer exists."
            )

        conn.execute(
            """
            UPDATE analytics.main.experiment_runs
            SET display_name = ?
            WHERE experiment_id = ?
            """,
            [display_name, experiment_id],
        )
    finally:
        conn.close()


def list_existing_tables(conn):
    rows = conn.execute(
        """
        SELECT table_name
        FROM duckdb_tables()
        WHERE database_name = 'analytics'
          AND schema_name = 'main'
        """
    ).fetchall()

    return {row[0] for row in rows}


def delete_experiment_runs(experiment_ids: list[str]) -> int:
    if not experiment_ids:
        return 0

    conn = get_connection()

    try:
        ensure_label_columns(conn)

        protected_id = get_protected_baseline_id(conn)

        ids = [
            str(experiment_id)
            for experiment_id in experiment_ids
            if experiment_id and experiment_id != protected_id
        ]

        if not ids:
            raise ValueError(
                "No deletable runs were selected. "
                "The protected main baseline cannot be removed."
            )

        existing = list_existing_tables(conn)

        for experiment_id in ids:
            for table in RUN_TABLES:
                if table not in existing:
                    continue

                conn.execute(
                    f"""
                    DELETE FROM analytics.main.{table}
                    WHERE experiment_id = ?
                    """,
                    [experiment_id],
                )

        return len(ids)
    finally:
        conn.close()


def list_completed_runs():
    conn = get_connection()

    try:
        ensure_label_columns(conn)

        return conn.execute(
            """
            SELECT
                experiment_id,
                experiment_name,
                experiment_type,
                parameter_name,
                parameter_value,
                top_n,
                transaction_cost_rate,
                status,
                created_at,
                display_name,
                COALESCE(is_protected, FALSE) AS is_protected,
                baseline_experiment_id
            FROM analytics.main.experiment_runs
            WHERE status = 'COMPLETED'
            ORDER BY
                COALESCE(is_protected, FALSE) DESC,
                created_at DESC
            """
        ).fetchdf()
    finally:
        conn.close()
