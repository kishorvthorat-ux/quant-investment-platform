from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC

import duckdb


DB_PATH = "duckdb/analytics.duckdb"


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


DEFAULT_GROUP_WEIGHTS = {
    "MOMENTUM": 0.40,
    "TREND": 0.25,
    "RISK": 0.20,
    "DRAWDOWN": 0.15,
}


DEFAULT_FACTOR_WEIGHTS = {
    "return_20d": 0.15,
    "return_60d": 0.15,
    "return_252d": 0.10,
    "price_vs_ma_20d": 0.08,
    "price_vs_ma_60d": 0.08,
    "price_vs_ma_252d": 0.09,
    "volatility_20d": 0.07,
    "volatility_60d": 0.07,
    "volatility_252d": 0.06,
    "drawdown_252d": 0.15,
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


@dataclass
class ExperimentVariant:
    experiment_id: str
    experiment_name: str
    experiment_type: str
    parameter_name: str
    parameter_value: float | None
    group_weights: dict
    factor_weights: dict
    top_n: int
    transaction_cost_rate: float


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
            relative_factor_weight = (
                factor_weights[factor] / factor_total
            )

            result[factor] = (
                group_weight * relative_factor_weight
            )

    return normalize_weights(result)


def make_variant(
    experiment_type: str,
    parameter_name: str,
    parameter_value: float | None,
    group_weights: dict[str, float],
    factor_weights: dict[str, float],
    top_n: int,
    transaction_cost_rate: float,
) -> ExperimentVariant:

    final_factor_weights = build_factor_weights(
        group_weights,
        factor_weights,
    )

    experiment_id = (
        ####datetime.utcnow().strftime("%Y%m%d%H%M%S")
	datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        + "_"
        + uuid.uuid4().hex[:6]
    )

    name = (
        f"{experiment_type}"
        f"_{parameter_name}"
        f"_{parameter_value}"
    )

    return ExperimentVariant(
        experiment_id=experiment_id,
        experiment_name=name,
        experiment_type=experiment_type,
        parameter_name=parameter_name,
        parameter_value=parameter_value,
        group_weights=normalize_weights(group_weights),
        factor_weights=final_factor_weights,
        top_n=top_n,
        transaction_cost_rate=transaction_cost_rate,
    )


def generate_factor_ablation_variants(
    top_n: int,
    transaction_cost_rate: float,
) -> list[ExperimentVariant]:

    variants = [
        make_variant(
            "FACTOR_ABLATION",
            "BASELINE",
            None,
            DEFAULT_GROUP_WEIGHTS.copy(),
            DEFAULT_FACTOR_WEIGHTS.copy(),
            top_n,
            transaction_cost_rate,
        )
    ]

    for group in DEFAULT_GROUP_WEIGHTS:

        groups = DEFAULT_GROUP_WEIGHTS.copy()
        groups[group] = 0.0

        variants.append(
            make_variant(
                "FACTOR_ABLATION",
                f"REMOVE_{group}",
                0.0,
                groups,
                DEFAULT_FACTOR_WEIGHTS.copy(),
                top_n,
                transaction_cost_rate,
            )
        )

    for factor in DEFAULT_FACTOR_WEIGHTS:
        factors = DEFAULT_FACTOR_WEIGHTS.copy()
        factors[factor] = 0.0
        variants.append(make_variant('SUBFACTOR_ABLATION', f'REMOVE_{factor.upper()}', 0.0, DEFAULT_GROUP_WEIGHTS.copy(), factors, top_n, transaction_cost_rate))

    return variants


def generate_group_weight_sensitivity_variants(
    group: str,
    values: list[float],
    top_n: int,
    transaction_cost_rate: float,
) -> list[ExperimentVariant]:

    if group not in DEFAULT_GROUP_WEIGHTS:
        raise ValueError(f"Unknown factor group: {group}")

    variants = []

    for value in values:

        groups = DEFAULT_GROUP_WEIGHTS.copy()
        groups[group] = value

        variants.append(
            make_variant(
                "WEIGHT_SENSITIVITY",
                group,
                value,
                groups,
                DEFAULT_FACTOR_WEIGHTS.copy(),
                top_n,
                transaction_cost_rate,
            )
        )

    return variants


def generate_top_n_variants(
    values: list[int],
    transaction_cost_rate: float,
) -> list[ExperimentVariant]:

    return [
        make_variant(
            "TOP_N_SENSITIVITY",
            "TOP_N",
            float(top_n),
            DEFAULT_GROUP_WEIGHTS.copy(),
            DEFAULT_FACTOR_WEIGHTS.copy(),
            top_n,
            transaction_cost_rate,
        )
        for top_n in values
    ]


def generate_cost_variants(
    values: list[float],
    top_n: int,
) -> list[ExperimentVariant]:

    return [
        make_variant(
            "COST_SENSITIVITY",
            "TRANSACTION_COST",
            cost,
            DEFAULT_GROUP_WEIGHTS.copy(),
            DEFAULT_FACTOR_WEIGHTS.copy(),
            top_n,
            cost,
        )
        for cost in values
    ]


def ensure_tables(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_runs (
            experiment_id VARCHAR PRIMARY KEY,
            experiment_name VARCHAR NOT NULL,
            experiment_type VARCHAR NOT NULL,
            parameter_name VARCHAR,
            parameter_value DOUBLE,
            top_n INTEGER NOT NULL,
            transaction_cost_rate DOUBLE NOT NULL,
            group_weights_json VARCHAR,
            factor_weights_json VARCHAR,
            status VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_run_factors (
            experiment_id VARCHAR,
            factor_group VARCHAR,
            feature_id VARCHAR,
            weight DOUBLE,
            direction INTEGER,
            enabled BOOLEAN,
            PRIMARY KEY (experiment_id, feature_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_scores (
            experiment_id VARCHAR,
            trade_date DATE,
            symbol VARCHAR,
            composite_score DOUBLE,
            rank INTEGER,
            selected_flag BOOLEAN
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_portfolios (
            experiment_id VARCHAR,
            trade_date DATE,
            symbol VARCHAR,
            rank INTEGER,
            target_weight DOUBLE,
            composite_score DOUBLE
        )
    """)


def save_variant(conn, variant: ExperimentVariant):

    conn.execute(
        """
        INSERT INTO analytics.main.experiment_runs (
            experiment_id,
            experiment_name,
            experiment_type,
            parameter_name,
            parameter_value,
            top_n,
            transaction_cost_rate,
            group_weights_json,
            factor_weights_json,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            variant.experiment_id,
            variant.experiment_name,
            variant.experiment_type,
            variant.parameter_name,
            variant.parameter_value,
            variant.top_n,
            variant.transaction_cost_rate,
            json.dumps(variant.group_weights),
            json.dumps(variant.factor_weights),
            "RUNNING",
        ],
    )

    for group, factors in FACTOR_GROUPS.items():

        for factor in factors:

            enabled = factor in variant.factor_weights
            weight = variant.factor_weights.get(factor, 0.0)

            conn.execute(
                """
                INSERT INTO analytics.main.experiment_run_factors (
                    experiment_id,
                    factor_group,
                    feature_id,
                    weight,
                    direction,
                    enabled
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    variant.experiment_id,
                    group,
                    factor,
                    weight,
                    DIRECTIONS[factor],
                    enabled,
                ],
            )


def run_scores(conn, variant: ExperimentVariant):

    rank_expression = {
        "return_20d": "return_20d_rank",
        "return_60d": "return_60d_rank",
        "return_252d": "return_252d_rank",
        "price_vs_ma_20d": "price_vs_ma_20d_rank",
        "price_vs_ma_60d": "price_vs_ma_60d_rank",
        "price_vs_ma_252d": "price_vs_ma_252d_rank",
        "volatility_20d": "(1 - volatility_20d_inverse_rank)",
        "volatility_60d": "(1 - volatility_60d_inverse_rank)",
        "volatility_252d": "(1 - volatility_252d_inverse_rank)",
        "drawdown_252d": "drawdown_252d_rank",
    }

    terms = []
    for factor, weight in variant.factor_weights.items():
        if weight == 0:
            continue
        terms.append(f"({rank_expression[factor]}) * {weight}")

    if not terms:
        raise ValueError("Experiment has no enabled factors.")

    composite_expression = " + ".join(terms)

    score_sql = f"""
        INSERT INTO analytics.main.experiment_scores
        SELECT
            '{variant.experiment_id}' AS experiment_id,
            trade_date,
            symbol,
            ({composite_expression}) AS composite_score,
            ROW_NUMBER() OVER (
                PARTITION BY trade_date
                ORDER BY ({composite_expression}) DESC, symbol
            ) AS rank,
            ROW_NUMBER() OVER (
                PARTITION BY trade_date
                ORDER BY ({composite_expression}) DESC, symbol
            ) <= {variant.top_n} AS selected_flag
        FROM (
            SELECT
                trade_date,
                symbol,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY return_20d) AS return_20d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY return_60d) AS return_60d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY return_252d) AS return_252d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY price_vs_ma_20d) AS price_vs_ma_20d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY price_vs_ma_60d) AS price_vs_ma_60d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY price_vs_ma_252d) AS price_vs_ma_252d_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY volatility_20d DESC) AS volatility_20d_inverse_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY volatility_60d DESC) AS volatility_60d_inverse_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY volatility_252d DESC) AS volatility_252d_inverse_rank,
                percent_rank() OVER (PARTITION BY trade_date ORDER BY drawdown_252d) AS drawdown_252d_rank
            FROM analytics.main.market_factors
            WHERE
                return_20d IS NOT NULL
                AND return_60d IS NOT NULL
                AND return_252d IS NOT NULL
                AND price_vs_ma_20d IS NOT NULL
                AND price_vs_ma_60d IS NOT NULL
                AND price_vs_ma_252d IS NOT NULL
                AND volatility_20d IS NOT NULL
                AND volatility_60d IS NOT NULL
                AND volatility_252d IS NOT NULL
                AND drawdown_252d IS NOT NULL
        ) ranked
    """

    conn.execute(score_sql)


def build_portfolio(conn, variant: ExperimentVariant):

    conn.execute(
        f"""
        INSERT INTO analytics.main.experiment_portfolios
        SELECT
            experiment_id,
            trade_date,
            symbol,
            rank,
            1.0 / {variant.top_n} AS target_weight,
            composite_score
        FROM analytics.main.experiment_scores
        WHERE experiment_id = '{variant.experiment_id}'
          AND selected_flag = TRUE
        """
    )


def mark_completed(conn, variant: ExperimentVariant):

    conn.execute(
        """
        UPDATE analytics.main.experiment_runs
        SET status = 'COMPLETED'
        WHERE experiment_id = ?
        """,
        [variant.experiment_id],
    )


def mark_failed(conn, variant: ExperimentVariant):

    conn.execute(
        """
        UPDATE analytics.main.experiment_runs
        SET status = 'FAILED'
        WHERE experiment_id = ?
        """,
        [variant.experiment_id],
    )


def run_variants(variants: list[ExperimentVariant]):

    conn = duckdb.connect(DB_PATH)

    ensure_tables(conn)

    for variant in variants:

        print(
            f"Running {variant.experiment_type}: "
            f"{variant.experiment_name}"
        )

        try:
            save_variant(conn, variant)
            run_scores(conn, variant)
            build_portfolio(conn, variant)
            mark_completed(conn, variant)

            print(
                f"  completed: {variant.experiment_id}"
            )

        except Exception as exc:

            mark_failed(conn, variant)

            print(
                f"  FAILED: {variant.experiment_id}: {exc}"
            )

    conn.close()


def main():

    parser = argparse.ArgumentParser(
        description="Quant R&D experiment engine"
    )

    parser.add_argument(
        "--experiment",
        choices=[
            "ablation",
            "weight",
            "topn",
            "cost",
        ],
        required=True,
    )

    parser.add_argument(
        "--group",
        default="MOMENTUM",
    )

    parser.add_argument(
        "--values",
        required=True,
        help="Comma-separated values",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--cost",
        type=float,
        default=0.002,
    )

    args = parser.parse_args()

    values = [
        float(value.strip())
        for value in args.values.split(",")
        if value.strip()
    ]

    if args.experiment == "ablation":

        variants = generate_factor_ablation_variants(
            args.top_n,
            args.cost,
        )

    elif args.experiment == "weight":

        variants = generate_group_weight_sensitivity_variants(
            args.group,
            values,
            args.top_n,
            args.cost,
        )

    elif args.experiment == "topn":

        variants = generate_top_n_variants(
            [int(v) for v in values],
            args.cost,
        )

    elif args.experiment == "cost":

        variants = generate_cost_variants(
            values,
            args.top_n,
        )

    else:
        raise ValueError("Unsupported experiment type")

    print(f"Generated {len(variants)} experiment variants")

    run_variants(variants)


if __name__ == "__main__":
    main()
