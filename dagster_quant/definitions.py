import subprocess
from pathlib import Path

import dagster as dg


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt" / "quant_dbt"
INGESTION_DIR = PROJECT_ROOT / "python" / "ingestion"


def run_script(script_name: str) -> str:
    result = subprocess.run(
        ["python", str(INGESTION_DIR / script_name)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{script_name} failed:\n\n"
            + result.stdout
            + "\n"
            + result.stderr
        )

    return result.stdout


def run_dbt() -> str:
    result = subprocess.run(
        [
            "dbt",
            "build",
            "--select",
            "+portfolio_performance_metrics_v2",
        ],
        cwd=DBT_PROJECT_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "dbt build failed:\n\n"
            + result.stdout
            + "\n"
            + result.stderr
        )

    return result.stdout


@dg.asset
def yahoo_market_data():
    return run_script("yahoo_market_data.py")


@dg.asset
def nse_trading_calendar():
    return run_script("ingest_nse_trading_calendar.py")


@dg.asset(deps=[yahoo_market_data])
def postgres_market_prices():
    return run_script("load_market_prices.py")


@dg.asset(deps=[nse_trading_calendar])
def postgres_trading_calendar():
    return run_script("load_official_trading_calendar.py")


@dg.asset(
    deps=[
        postgres_market_prices,
        postgres_trading_calendar,
    ]
)
def dbt_v2_performance_build():
    return run_dbt()

daily_quant_pipeline = dg.ScheduleDefinition(
    name="daily_quant_pipeline",
    cron_schedule="30 15 * * 1-5",
    target=[dbt_v2_performance_build],
)
defs = dg.Definitions(
    assets=[
        yahoo_market_data,
        nse_trading_calendar,
        postgres_market_prices,
        postgres_trading_calendar,
        dbt_v2_performance_build,
    ],
    schedules=[daily_quant_pipeline],
)
