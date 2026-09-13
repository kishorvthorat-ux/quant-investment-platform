from __future__ import annotations

import re
import shutil
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt" / "quant_dbt"
V2_DBT_SELECT = (
    "+portfolio_performance_metrics_v2",
    "+weekly_signals_v2",
    "+trade_orders_v2",
)

PROTECTED_CONFIGURATION_IDS = (1, 2)
PROTECTED_STRATEGY_IDS = (
    "M_RD_504010",
    "M_RD_504010_V2",
)
TEMPLATE_CONFIGURATION_ID = 2
TEMPLATE_STRATEGY_ID = "M_RD_504010_V2"

FACTOR_GROUPS = {
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

DIRECTIONS = {
    "return_20d": 1,
    "return_60d": 1,
    "return_252d": 1,
    "price_vs_ma_20d": 1,
    "price_vs_ma_60d": 1,
    "price_vs_ma_252d": 1,
    "volatility_20d": -1,
    "volatility_60d": -1,
    "volatility_252d": -1,
    "drawdown_252d": 1,
}

GROUP_NAMES = {
    "MOMENTUM": "Momentum",
    "TREND": "Trend",
    "RISK": "Risk",
    "DRAWDOWN": "Drawdown",
}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())

    if total <= 0:
        raise ValueError("Weight total must be greater than zero.")

    return {
        key: value / total
        for key, value in weights.items()
        if value > 0
    }


def build_factor_weights(
    group_weights: dict[str, float],
    factor_weights: dict[str, float],
) -> dict[str, float]:

    normalized_groups = normalize_weights(group_weights)
    result = {}

    for group, group_weight in normalized_groups.items():
        factors = FACTOR_GROUPS[group]
        enabled_factors = [
            factor
            for factor in factors
            if factor in factor_weights and factor_weights[factor] > 0
        ]

        if not enabled_factors:
            continue

        factor_total = sum(
            factor_weights[factor]
            for factor in enabled_factors
        )

        for factor in enabled_factors:
            result[factor] = (
                group_weight * (factor_weights[factor] / factor_total)
            )

    return normalize_weights(result)


def to_feature_id(research_feature_id: str) -> str:
    return str(research_feature_id).upper()


def to_direction(research_feature_id: str) -> str:
    if DIRECTIONS.get(research_feature_id, 1) < 0:
        return "NEGATIVE"
    return "POSITIVE"


def money_weight(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )


def _allocate_exact_parts(
    target: Decimal,
    parts: list[Decimal],
) -> list[Decimal]:
    if not parts:
        return []

    raw_total = sum(parts)

    if raw_total <= 0:
        even = (target / Decimal(len(parts))).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )
        allocated = [even] * len(parts)
        allocated[-1] = money_weight(target - sum(allocated[:-1]))
        return allocated

    scaled = [
        money_weight(target * (part / raw_total))
        for part in parts
    ]
    scaled[-1] = money_weight(target - sum(scaled[:-1]))
    return scaled


def build_promotion_snapshot(
    group_weights: dict[str, float],
    factor_weights: dict[str, float],
    factor_enabled: dict[str, bool],
    top_n: int,
    transaction_cost_rate: float,
    strategy_name: str,
):
    name = str(strategy_name or "").strip()

    if not name:
        raise ValueError("Enter a production configuration name.")

    effective_factor_weights = {}

    for feature_id, enabled in factor_enabled.items():
        if enabled:
            effective_factor_weights[feature_id] = float(
                factor_weights.get(feature_id, 0.0)
            )
        else:
            effective_factor_weights[feature_id] = 0.0

    normalized_groups = normalize_weights(group_weights)

    if sum(normalized_groups.values()) <= 0:
        raise ValueError(
            "At least one factor group must have a weight greater than zero."
        )

    enabled_groups = [
        group
        for group in FACTOR_GROUPS
        if float(normalized_groups.get(group, 0.0)) > 0
    ]

    if not enabled_groups:
        raise ValueError(
            "At least one factor group must have a weight greater than zero."
        )

    group_targets = _allocate_exact_parts(
        Decimal("1.000000"),
        [
            Decimal(str(normalized_groups.get(group, 0.0)))
            for group in enabled_groups
        ],
    )
    group_target_map = dict(zip(enabled_groups, group_targets))

    groups = []
    factors = []

    for group, features in FACTOR_GROUPS.items():
        group_weight = group_target_map.get(group, Decimal("0"))
        group_enabled = group in group_target_map

        enabled_in_group = [
            feature_id
            for feature_id in features
            if effective_factor_weights.get(feature_id, 0.0) > 0
        ]

        if group_enabled and not enabled_in_group:
            raise ValueError(
                f"{GROUP_NAMES.get(group, group)} has weight but no "
                "enabled factors."
            )

        groups.append(
            {
                "factor_group_id": group,
                "factor_group_name": GROUP_NAMES.get(group, group.title()),
                "group_weight": group_weight,
                "enabled": group_enabled,
            }
        )

        feature_parts = [
            Decimal(str(effective_factor_weights.get(feature_id, 0.0)))
            for feature_id in enabled_in_group
        ]
        allocated = (
            _allocate_exact_parts(group_weight, feature_parts)
            if group_enabled
            else []
        )
        allocated_map = dict(zip(enabled_in_group, allocated))

        for feature_id in features:
            feature_on = (
                group_enabled and feature_id in allocated_map
            )
            factors.append(
                {
                    "factor_group_id": group,
                    "feature_id": to_feature_id(feature_id),
                    "feature_weight": (
                        allocated_map.get(feature_id, Decimal("0"))
                    ),
                    "direction": to_direction(feature_id),
                    "enabled": feature_on,
                }
            )

    enabled_feature_total = sum(
        Decimal(row["feature_weight"])
        for row in factors
        if row["enabled"]
    )

    if abs(enabled_feature_total - Decimal("1.000000")) > Decimal("0.000001"):
        raise ValueError(
            "Enabled factor weights must sum to 1 after normalization."
        )

    return {
        "strategy_name": name,
        "top_n": int(top_n),
        "position_weight": position_weight_for_top_n(top_n),
        "transaction_cost_rate": money_weight(transaction_cost_rate),
        "groups": groups,
        "factors": factors,
    }


def position_weight_for_top_n(top_n: int) -> Decimal:
    if int(top_n) < 1:
        raise ValueError("Top N must be at least 1.")

    return (
        Decimal(1) / Decimal(int(top_n))
    ).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def promote_rnd_configuration(
    group_weights: dict[str, float],
    factor_weights: dict[str, float],
    factor_enabled: dict[str, bool],
    top_n: int,
    transaction_cost_rate: float,
    strategy_name: str,
    target_status: str = "DRAFT",
) -> dict:
    target_status = str(target_status or "DRAFT").upper()

    if target_status not in ("DRAFT", "VALIDATED"):
        raise ValueError("target_status must be DRAFT or VALIDATED.")

    snapshot = build_promotion_snapshot(
        group_weights,
        factor_weights,
        factor_enabled,
        top_n,
        transaction_cost_rate,
        strategy_name,
    )

    live_status = (
        "ACTIVE" if target_status == "VALIDATED" else "DRAFT"
    )

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT strategy_id
                    FROM analytics.strategy_config
                    WHERE strategy_id = %s
                    FOR UPDATE
                    """,
                    [TEMPLATE_STRATEGY_ID],
                )

                if cur.fetchone() is None:
                    raise RuntimeError(
                        f"Production strategy {TEMPLATE_STRATEGY_ID} "
                        "was not found."
                    )

                new_strategy_id = _unused_strategy_id(
                    cur,
                    snapshot["strategy_name"],
                )

                overrides = {
                    "strategy_id": new_strategy_id,
                    "strategy_name": snapshot["strategy_name"],
                    "configuration_version": 1,
                    "top_n": snapshot["top_n"],
                    "position_weight": snapshot["position_weight"],
                    "transaction_cost_rate": snapshot[
                        "transaction_cost_rate"
                    ],
                    "status": live_status,
                }
                live_columns = set(_table_columns(cur, "strategy_config"))
                overrides = {
                    key: value
                    for key, value in overrides.items()
                    if key in live_columns
                }

                try:
                    with conn.transaction():
                        _clone_strategy_config(
                            cur,
                            TEMPLATE_STRATEGY_ID,
                            overrides,
                        )
                except Exception:
                    if live_status != "DRAFT":
                        raise

                    overrides["status"] = "ACTIVE"
                    _clone_strategy_config(
                        cur,
                        TEMPLATE_STRATEGY_ID,
                        overrides,
                    )

                configuration_id = _insert_version_snapshot(
                    cur,
                    new_strategy_id,
                    snapshot,
                    target_status,
                )

                if configuration_id in PROTECTED_CONFIGURATION_IDS:
                    raise RuntimeError(
                        "Promotion tried to reuse a protected "
                        "configuration_id. Transaction aborted."
                    )

                _copy_version_factors_to_strategy(
                    cur,
                    configuration_id,
                    new_strategy_id,
                )

                cur.execute(
                    """
                    SELECT configuration_id
                    FROM analytics.strategy_config_version
                    WHERE configuration_id = ANY(%s)
                    """,
                    [list(PROTECTED_CONFIGURATION_IDS)],
                )
                protected_rows = {
                    int(row[0]) for row in cur.fetchall()
                }

                if set(PROTECTED_CONFIGURATION_IDS) - protected_rows:
                    raise RuntimeError(
                        "Protected production configurations are missing."
                    )

    return {
        "configuration_id": configuration_id,
        "configuration_version": 1,
        "strategy_id": new_strategy_id,
        "status": target_status,
        "strategy_name": snapshot["strategy_name"],
    }


def _insert_version_snapshot(
    cur,
    strategy_id: str,
    snapshot: dict,
    status: str,
) -> int:
    cur.execute(
        """
        INSERT INTO analytics.strategy_config_version (
            strategy_id,
            configuration_version,
            strategy_name,
            momentum_weight,
            risk_weight,
            drawdown_weight,
            trend_weight,
            top_n,
            position_weight,
            transaction_cost_rate,
            signal_frequency,
            entry_rule,
            rebalance_rule,
            configuration_type,
            status
        )
        SELECT
            %s,
            1,
            %s,
            momentum_weight,
            risk_weight,
            drawdown_weight,
            trend_weight,
            %s,
            %s,
            %s,
            signal_frequency,
            entry_rule,
            rebalance_rule,
            configuration_type,
            %s
        FROM analytics.strategy_config_version
        WHERE configuration_id = %s
        RETURNING configuration_id
        """,
        [
            strategy_id,
            snapshot["strategy_name"],
            snapshot["top_n"],
            snapshot["position_weight"],
            snapshot["transaction_cost_rate"],
            status,
            TEMPLATE_CONFIGURATION_ID,
        ],
    )
    configuration_id = int(cur.fetchone()[0])

    for group in snapshot["groups"]:
        cur.execute(
            """
            INSERT INTO analytics.strategy_config_version_factor_group (
                configuration_id,
                factor_group_id,
                factor_group_name,
                group_weight,
                enabled
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                configuration_id,
                group["factor_group_id"],
                group["factor_group_name"],
                group["group_weight"],
                group["enabled"],
            ],
        )

    for factor in snapshot["factors"]:
        cur.execute(
            """
            INSERT INTO analytics.strategy_config_version_factor (
                configuration_id,
                factor_group_id,
                feature_id,
                feature_weight,
                direction,
                enabled
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                configuration_id,
                factor["factor_group_id"],
                factor["feature_id"],
                factor["feature_weight"],
                factor["direction"],
                factor["enabled"],
            ],
        )

    return configuration_id


def _safe_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        raise RuntimeError(f"Unsafe column name: {name}")
    return name


def _table_columns(cur, table_name: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'analytics'
          AND table_name = %s
          AND COALESCE(is_identity, 'NO') <> 'YES'
        ORDER BY ordinal_position
        """,
        [table_name],
    )
    return [_safe_ident(row[0]) for row in cur.fetchall()]


def _column_defaults(cur, table_name: str) -> dict[str, str | None]:
    cur.execute(
        """
        SELECT column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = 'analytics'
          AND table_name = %s
        """,
        [table_name],
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def build_strategy_id(strategy_name: str, suffix: str | None = None) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", strategy_name or "")
    slug = slug.strip("_").upper() or "RND"
    slug = slug[:36]

    if suffix:
        slug = f"{slug}_{suffix}"

    return slug[:50]


def _unused_strategy_id(
    cur,
    strategy_name: str,
    suffix: str | None = None,
) -> str:
    base = build_strategy_id(strategy_name, suffix)
    candidate = base
    extra = 2

    while True:
        if candidate in PROTECTED_STRATEGY_IDS:
            candidate = f"RND_{candidate}"[:50]
            continue

        cur.execute(
            """
            SELECT 1
            FROM analytics.strategy_config
            WHERE strategy_id = %s
            """,
            [candidate],
        )

        if cur.fetchone() is None:
            return candidate

        trimmed = base[: max(1, 50 - len(str(extra)) - 1)]
        candidate = f"{trimmed}_{extra}"[:50]
        extra += 1


def _clone_strategy_config(
    cur,
    source_strategy_id: str,
    overrides: dict,
):
    columns = _table_columns(cur, "strategy_config")
    defaults = _column_defaults(cur, "strategy_config")
    insert_cols = []
    select_parts = []
    params = []

    for column in columns:
        if column in ("created_at", "updated_at") and defaults.get(column):
            continue

        insert_cols.append(column)

        if column in overrides:
            select_parts.append("%s")
            params.append(overrides[column])
        else:
            select_parts.append(column)

    params.append(source_strategy_id)

    cur.execute(
        f"""
        INSERT INTO analytics.strategy_config (
            {", ".join(insert_cols)}
        )
        SELECT {", ".join(select_parts)}
        FROM analytics.strategy_config
        WHERE strategy_id = %s
        """,
        params,
    )


def _copy_version_factors_to_strategy(
    cur,
    configuration_id: int,
    strategy_id: str,
):
    group_version = set(
        _table_columns(cur, "strategy_config_version_factor_group")
    )
    group_defaults = _column_defaults(cur, "strategy_factor_groups")
    group_insert = ["strategy_id"]
    group_select = ["%s"]
    group_params = [strategy_id]

    for column in _table_columns(cur, "strategy_factor_groups"):
        if column == "strategy_id":
            continue
        if column in ("created_at", "updated_at") and group_defaults.get(column):
            continue
        if column not in group_version:
            continue
        group_insert.append(column)
        group_select.append(column)

    group_params.append(configuration_id)
    cur.execute(
        f"""
        INSERT INTO analytics.strategy_factor_groups (
            {", ".join(group_insert)}
        )
        SELECT {", ".join(group_select)}
        FROM analytics.strategy_config_version_factor_group
        WHERE configuration_id = %s
        """,
        group_params,
    )

    factor_version = set(
        _table_columns(cur, "strategy_config_version_factor")
    )
    factor_defaults = _column_defaults(cur, "strategy_factors")
    factor_insert = ["strategy_id"]
    factor_select = ["%s"]
    factor_params = [strategy_id]

    for column in _table_columns(cur, "strategy_factors"):
        if column == "strategy_id":
            continue
        if column in ("created_at", "updated_at") and factor_defaults.get(column):
            continue
        if column not in factor_version:
            continue
        factor_insert.append(column)
        factor_select.append(column)

    factor_params.append(configuration_id)
    cur.execute(
        f"""
        INSERT INTO analytics.strategy_factors (
            {", ".join(factor_insert)}
        )
        SELECT {", ".join(factor_select)}
        FROM analytics.strategy_config_version_factor
        WHERE configuration_id = %s
        """,
        factor_params,
    )


def _create_strategy_from_draft(cur, current: dict) -> str:
    new_strategy_id = _unused_strategy_id(
        cur,
        current["strategy_name"],
        current["configuration_id"],
    )

    overrides = {
        "strategy_id": new_strategy_id,
        "strategy_name": current["strategy_name"],
        "configuration_version": 1,
        "top_n": current["top_n"],
        "position_weight": current["position_weight"],
        "transaction_cost_rate": current["transaction_cost_rate"],
        "status": "ACTIVE",
    }

    live_columns = set(_table_columns(cur, "strategy_config"))
    overrides = {
        key: value
        for key, value in overrides.items()
        if key in live_columns
    }

    _clone_strategy_config(cur, TEMPLATE_STRATEGY_ID, overrides)
    _copy_version_factors_to_strategy(
        cur,
        current["configuration_id"],
        new_strategy_id,
    )

    return new_strategy_id


def _require_unprotected(configuration_id: int) -> int:
    cid = int(configuration_id)

    if cid in PROTECTED_CONFIGURATION_IDS:
        raise RuntimeError(
            "Configs 1 and 2 are protected and cannot be changed "
            "or deleted from Configuration Manager."
        )

    return cid


def _lock_configuration(cur, configuration_id: int):
    cur.execute(
        """
        SELECT
            configuration_id,
            status,
            strategy_id,
            strategy_name,
            top_n,
            position_weight,
            transaction_cost_rate
        FROM analytics.strategy_config_version
        WHERE configuration_id = %s
        FOR UPDATE
        """,
        [configuration_id],
    )
    row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            f"Configuration {configuration_id} was not found."
        )

    (
        cid,
        status,
        strategy_id,
        strategy_name,
        top_n,
        position_weight,
        transaction_cost_rate,
    ) = row
    _require_unprotected(cid)

    return {
        "configuration_id": int(cid),
        "status": str(status),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "top_n": top_n,
        "position_weight": position_weight,
        "transaction_cost_rate": transaction_cost_rate,
    }


def _set_status(configuration_id: int, new_status: str, allowed_from: tuple[str, ...]) -> dict:
    cid = _require_unprotected(configuration_id)

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                current = _lock_configuration(cur, cid)

                if current["status"] not in allowed_from:
                    allowed = ", ".join(allowed_from)
                    raise RuntimeError(
                        f"Cannot set {current['strategy_name']} "
                        f"(config {cid}) to {new_status} from "
                        f"{current['status']}. Allowed source "
                        f"status: {allowed}."
                    )

                cur.execute(
                    """
                    UPDATE analytics.strategy_config_version
                    SET status = %s
                    WHERE configuration_id = %s
                      AND configuration_id <> ALL(%s)
                      AND status = ANY(%s)
                    RETURNING
                        configuration_id,
                        status,
                        strategy_id,
                        strategy_name
                    """,
                    [
                        new_status,
                        cid,
                        list(PROTECTED_CONFIGURATION_IDS),
                        list(allowed_from),
                    ],
                )
                updated = cur.fetchone()

                if updated is None:
                    raise RuntimeError(
                        "Status was not updated. The configuration "
                        "may be protected or already changed."
                    )

    return {
        "configuration_id": int(updated[0]),
        "status": str(updated[1]),
        "strategy_id": updated[2],
        "strategy_name": updated[3],
    }


def validate_draft_configuration(configuration_id: int) -> dict:
    cid = _require_unprotected(configuration_id)

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                current = _lock_configuration(cur, cid)

                if current["status"] not in ("DRAFT", "VALIDATED"):
                    raise RuntimeError(
                        "Only DRAFT snapshots, or VALIDATED snapshots "
                        "still attached to M_RD_504010_V2, can become "
                        f"a strategy. Config {cid} is {current['status']}."
                    )

                strategy_id = current["strategy_id"]
                already_own_strategy = (
                    strategy_id not in PROTECTED_STRATEGY_IDS
                )

                if already_own_strategy:
                    if current["status"] == "VALIDATED":
                        raise RuntimeError(
                            f"Config {cid} is already strategy "
                            f"{strategy_id}."
                        )

                    cur.execute(
                        """
                        UPDATE analytics.strategy_config_version
                        SET status = 'VALIDATED'
                        WHERE configuration_id = %s
                          AND configuration_id <> ALL(%s)
                          AND status = 'DRAFT'
                        RETURNING
                            configuration_id,
                            status,
                            strategy_id,
                            strategy_name
                        """,
                        [
                            cid,
                            list(PROTECTED_CONFIGURATION_IDS),
                        ],
                    )
                else:
                    strategy_id = _create_strategy_from_draft(
                        cur,
                        current,
                    )

                    cur.execute(
                        """
                        UPDATE analytics.strategy_config_version
                        SET
                            strategy_id = %s,
                            configuration_version = 1,
                            status = 'VALIDATED'
                        WHERE configuration_id = %s
                          AND configuration_id <> ALL(%s)
                          AND status = ANY(%s)
                        RETURNING
                            configuration_id,
                            status,
                            strategy_id,
                            strategy_name
                        """,
                        [
                            strategy_id,
                            cid,
                            list(PROTECTED_CONFIGURATION_IDS),
                            ["DRAFT", "VALIDATED"],
                        ],
                    )

                updated = cur.fetchone()

                if updated is None:
                    raise RuntimeError(
                        "Validation did not apply. The configuration "
                        "may be protected or already changed."
                    )

    return {
        "configuration_id": int(updated[0]),
        "status": str(updated[1]),
        "strategy_id": updated[2],
        "strategy_name": updated[3],
    }


def freeze_configuration(configuration_id: int) -> dict:
    return _set_status(
        configuration_id,
        "FROZEN",
        ("VALIDATED",),
    )


def retire_configuration(configuration_id: int) -> dict:
    return _set_status(
        configuration_id,
        "RETIRED",
        ("DRAFT", "VALIDATED", "FROZEN"),
    )


def delete_configuration(configuration_id: int) -> dict:
    cid = _require_unprotected(configuration_id)

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                current = _lock_configuration(cur, cid)

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'analytics'
                          AND table_name = 'backtest_runs'
                    )
                    """
                )
                has_backtests = bool(cur.fetchone()[0])
                backtest_count = 0

                if has_backtests:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM analytics.backtest_runs
                        WHERE configuration_id = %s
                        """,
                        [cid],
                    )
                    backtest_count = int(cur.fetchone()[0])

                if backtest_count > 0:
                    raise RuntimeError(
                        f"Config {cid} has {backtest_count} backtest "
                        "run(s) attached. Retire it instead of deleting."
                    )

                cur.execute(
                    """
                    DELETE FROM analytics.strategy_config_version_factor
                    WHERE configuration_id = %s
                      AND configuration_id <> ALL(%s)
                    """,
                    [cid, list(PROTECTED_CONFIGURATION_IDS)],
                )
                cur.execute(
                    """
                    DELETE FROM analytics.strategy_config_version_factor_group
                    WHERE configuration_id = %s
                      AND configuration_id <> ALL(%s)
                    """,
                    [cid, list(PROTECTED_CONFIGURATION_IDS)],
                )
                cur.execute(
                    """
                    DELETE FROM analytics.strategy_config_version
                    WHERE configuration_id = %s
                      AND configuration_id <> ALL(%s)
                    RETURNING configuration_id, strategy_name
                    """,
                    [cid, list(PROTECTED_CONFIGURATION_IDS)],
                )
                deleted = cur.fetchone()

                if deleted is None:
                    raise RuntimeError(
                        "Delete did not apply. The configuration "
                        "may be protected."
                    )

                leftover_strategy = current["strategy_id"]

                if leftover_strategy not in PROTECTED_STRATEGY_IDS:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM analytics.strategy_config_version
                        WHERE strategy_id = %s
                        """,
                        [leftover_strategy],
                    )
                    remaining = int(cur.fetchone()[0])

                    if remaining == 0:
                        cur.execute(
                            """
                            DELETE FROM analytics.strategy_factors
                            WHERE strategy_id = %s
                            """,
                            [leftover_strategy],
                        )
                        cur.execute(
                            """
                            DELETE FROM analytics.strategy_factor_groups
                            WHERE strategy_id = %s
                            """,
                            [leftover_strategy],
                        )
                        cur.execute(
                            """
                            DELETE FROM analytics.strategy_config
                            WHERE strategy_id = %s
                            """,
                            [leftover_strategy],
                        )

    return {
        "configuration_id": int(deleted[0]),
        "strategy_name": deleted[1],
        "previous_status": current["status"],
    }


def _repair_snapshot_configuration(cur, configuration_id: int) -> bool:
    cur.execute(
        """
        SELECT factor_group_id, group_weight, enabled
        FROM analytics.strategy_config_version_factor_group
        WHERE configuration_id = %s
        """,
        [configuration_id],
    )
    groups = cur.fetchall()

    cur.execute(
        """
        SELECT factor_group_id, feature_id, feature_weight, enabled
        FROM analytics.strategy_config_version_factor
        WHERE configuration_id = %s
        ORDER BY factor_group_id, feature_id
        """,
        [configuration_id],
    )
    factors = cur.fetchall()

    enabled_groups = [
        row for row in groups if bool(row[2]) and Decimal(str(row[1])) > 0
    ]

    if not enabled_groups:
        return False

    new_group_weights = dict(
        zip(
            [row[0] for row in enabled_groups],
            _allocate_exact_parts(
                Decimal("1.000000"),
                [Decimal(str(row[1])) for row in enabled_groups],
            ),
        )
    )

    changed = False

    for group_id, group_weight, enabled in groups:
        target = (
            new_group_weights.get(group_id, Decimal("0"))
            if enabled
            else Decimal("0")
        )

        if money_weight(group_weight) != target or bool(enabled) != (target > 0):
            cur.execute(
                """
                UPDATE analytics.strategy_config_version_factor_group
                SET group_weight = %s,
                    enabled = %s
                WHERE configuration_id = %s
                  AND factor_group_id = %s
                  AND configuration_id <> ALL(%s)
                """,
                [
                    target,
                    target > 0,
                    configuration_id,
                    group_id,
                    list(PROTECTED_CONFIGURATION_IDS),
                ],
            )
            changed = True

        group_factors = [
            row for row in factors if row[0] == group_id
        ]
        enabled_factors = [
            row for row in group_factors if bool(row[3])
        ]

        if target > 0 and enabled_factors:
            allocated = _allocate_exact_parts(
                target,
                [Decimal(str(row[2])) for row in enabled_factors],
            )
            allocated_map = {
                row[1]: weight
                for row, weight in zip(enabled_factors, allocated)
            }
        else:
            allocated_map = {}

        for group_id_f, feature_id, feature_weight, feature_enabled in group_factors:
            new_weight = allocated_map.get(feature_id, Decimal("0"))
            new_enabled = feature_id in allocated_map

            if (
                money_weight(feature_weight) != new_weight
                or bool(feature_enabled) != new_enabled
            ):
                cur.execute(
                    """
                    UPDATE analytics.strategy_config_version_factor
                    SET feature_weight = %s,
                        enabled = %s
                    WHERE configuration_id = %s
                      AND factor_group_id = %s
                      AND feature_id = %s
                      AND configuration_id <> ALL(%s)
                    """,
                    [
                        new_weight,
                        new_enabled,
                        configuration_id,
                        group_id_f,
                        feature_id,
                        list(PROTECTED_CONFIGURATION_IDS),
                    ],
                )
                changed = True

    return changed


def _repair_live_strategy_weights(cur, strategy_id: str) -> None:
    if strategy_id in PROTECTED_STRATEGY_IDS:
        return

    cur.execute(
        """
        SELECT factor_group_id, group_weight, enabled
        FROM analytics.strategy_factor_groups
        WHERE strategy_id = %s
        """,
        [strategy_id],
    )
    groups = cur.fetchall()

    cur.execute(
        """
        SELECT factor_group_id, feature_id, feature_weight, enabled
        FROM analytics.strategy_factors
        WHERE strategy_id = %s
        ORDER BY factor_group_id, feature_id
        """,
        [strategy_id],
    )
    factors = cur.fetchall()

    enabled_groups = [
        row for row in groups if bool(row[2]) and Decimal(str(row[1])) > 0
    ]

    if not enabled_groups:
        return

    new_group_weights = dict(
        zip(
            [row[0] for row in enabled_groups],
            _allocate_exact_parts(
                Decimal("1.000000"),
                [Decimal(str(row[1])) for row in enabled_groups],
            ),
        )
    )

    for group_id, group_weight, enabled in groups:
        target = (
            new_group_weights.get(group_id, Decimal("0"))
            if enabled
            else Decimal("0")
        )
        cur.execute(
            """
            UPDATE analytics.strategy_factor_groups
            SET group_weight = %s,
                enabled = %s
            WHERE strategy_id = %s
              AND factor_group_id = %s
            """,
            [target, target > 0, strategy_id, group_id],
        )

        group_factors = [
            row for row in factors if row[0] == group_id
        ]
        enabled_factors = [
            row for row in group_factors if bool(row[3])
        ]

        if target > 0 and enabled_factors:
            allocated = _allocate_exact_parts(
                target,
                [Decimal(str(row[2])) for row in enabled_factors],
            )
            allocated_map = {
                row[1]: weight
                for row, weight in zip(enabled_factors, allocated)
            }
        else:
            allocated_map = {}

        for group_id_f, feature_id, _weight, _enabled in group_factors:
            cur.execute(
                """
                UPDATE analytics.strategy_factors
                SET feature_weight = %s,
                    enabled = %s
                WHERE strategy_id = %s
                  AND factor_group_id = %s
                  AND feature_id = %s
                """,
                [
                    allocated_map.get(feature_id, Decimal("0")),
                    feature_id in allocated_map,
                    strategy_id,
                    group_id_f,
                    feature_id,
                ],
            )


def repair_unprotected_snapshot_weights() -> int:
    repaired = 0

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT configuration_id, strategy_id
                    FROM analytics.strategy_config_version
                    WHERE configuration_id <> ALL(%s)
                    """,
                    [list(PROTECTED_CONFIGURATION_IDS)],
                )
                rows = cur.fetchall()

                for configuration_id, strategy_id in rows:
                    if _repair_snapshot_configuration(
                        cur,
                        int(configuration_id),
                    ):
                        repaired += 1

                    if strategy_id not in PROTECTED_STRATEGY_IDS:
                        _repair_live_strategy_weights(
                            cur,
                            strategy_id,
                        )

    return repaired


def run_production_v2_dbt() -> str:
    repair_unprotected_snapshot_weights()

    dbt_bin = Path(sys.executable).parent / "dbt"

    if not dbt_bin.exists():
        found = shutil.which("dbt")
        if not found:
            raise RuntimeError(
                "dbt was not found. Run production from the "
                "project virtualenv."
            )
        dbt_bin = Path(found)

    result = subprocess.run(
        [
            str(dbt_bin),
            "build",
            "--select",
            *V2_DBT_SELECT,
        ],
        cwd=str(DBT_PROJECT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    tail = "\n".join(output.splitlines()[-40:])

    if result.returncode != 0:
        raise RuntimeError(
            "Production V2 dbt build failed.\n" + tail
        )

    return tail
