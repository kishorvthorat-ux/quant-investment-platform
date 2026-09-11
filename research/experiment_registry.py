from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = PROJECT_ROOT / "duckdb" / "analytics.duckdb"

with duckdb.connect(str(DUCKDB_PATH)) as con:
    con.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiments (
            experiment_id VARCHAR PRIMARY KEY,
            base_configuration_id BIGINT,
            experiment_type VARCHAR NOT NULL,
            experiment_name VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'DRAFT',
            top_n INTEGER,
            transaction_cost_rate DOUBLE,
            start_date DATE,
            end_date DATE,
            parameters_json VARCHAR,
            result_summary VARCHAR,
            decision VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_factor_groups (
            experiment_id VARCHAR,
            factor_group_id VARCHAR,
            enabled BOOLEAN,
            group_weight DOUBLE,
            PRIMARY KEY (experiment_id, factor_group_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_factors (
            experiment_id VARCHAR,
            factor_group_id VARCHAR,
            feature_id VARCHAR,
            enabled BOOLEAN,
            feature_weight DOUBLE,
            direction VARCHAR,
            PRIMARY KEY (experiment_id, feature_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS analytics.main.experiment_results (
            experiment_id VARCHAR,
            metric_name VARCHAR,
            metric_value DOUBLE,
            evaluation_period VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (experiment_id, metric_name, evaluation_period)
        )
    """)

    print("R&D experiment registry initialized")
    print(
        con.execute("""
            SELECT table_name
            FROM duckdb_tables()
            WHERE database_name = 'analytics'
              AND schema_name = 'main'
              AND table_name LIKE 'experiment%'
            ORDER BY table_name
        """).fetchall()
    )
