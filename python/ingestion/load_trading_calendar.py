import os
from pathlib import Path

import polars as pl
import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

INPUT_FILE = Path("data/raw/market/trading_calendar.parquet")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5434")),
    "database": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


df = pl.read_parquet(INPUT_FILE)

conn = psycopg2.connect(**DB_CONFIG)

try:
    with conn.cursor() as cur:

        for row in df.iter_rows(named=True):

            cur.execute(
                """
                INSERT INTO raw.trading_calendar (
                    trade_date,
                    exchange,
                    is_trading_day,
                    holiday_name
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (trade_date)
                DO UPDATE SET
                    exchange = EXCLUDED.exchange,
                    is_trading_day = EXCLUDED.is_trading_day,
                    holiday_name = EXCLUDED.holiday_name
                """,
                (
                    row["trade_date"],
                    row["exchange"],
                    row["is_trading_day"],
                    row["holiday_name"],
                ),
            )

    conn.commit()

finally:
    conn.close()

print(f"Rows loaded: {df.height:,}")
print("Trading calendar load completed.")
