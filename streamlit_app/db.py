import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5434"),
        dbname=os.getenv("POSTGRES_DB", "quant_platform"),
        user=os.getenv("POSTGRES_USER", "quant_user"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def query_df(sql: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)
