import os
from pathlib import Path

import polars as pl
import psycopg2
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv(dotenv_path=".env")

INPUT_FILE = Path(
    "data/raw/market/yahoo_equities.parquet"
)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5434")),
    "database": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


# ============================================================
# LOAD PARQUET
# ============================================================

print("=" * 70)
print("LOADING MARKET DATA INTO POSTGRESQL")
print("=" * 70)

print(f"\nInput file: {INPUT_FILE}")

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Market data file not found: {INPUT_FILE}"
    )

df = pl.read_parquet(INPUT_FILE)

print(f"Rows read: {df.height:,}")
print(f"Symbols:   {df.select('symbol').n_unique()}")
print(
    f"Date range: {df['trade_date'].min()} "
    f"to {df['trade_date'].max()}"
)


# ============================================================
# BASIC VALIDATION
# ============================================================

required_columns = {
    "trade_date",
    "symbol",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
}

missing_columns = required_columns - set(df.columns)

if missing_columns:
    raise ValueError(
        f"Missing required columns: {sorted(missing_columns)}"
    )


duplicate_count = (
    df.group_by(
        ["trade_date", "symbol", "exchange"]
    )
    .len()
    .filter(pl.col("len") > 1)
    .height
)

if duplicate_count > 0:
    raise ValueError(
        f"Found {duplicate_count:,} duplicate market-price keys."
    )

print("Validation: PASSED")


# ============================================================
# DATABASE CONNECTION
# ============================================================

print("\nConnecting to PostgreSQL...")

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

print("PostgreSQL connection: OK")


# ============================================================
# UPSERT
# ============================================================

insert_sql = """
INSERT INTO raw.market_prices (
    trade_date,
    symbol,
    exchange,
    open,
    high,
    low,
    close,
    adjusted_close,
    volume,
    source
)
VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s
)
ON CONFLICT (
    trade_date,
    symbol,
    exchange
)
DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    adjusted_close = EXCLUDED.adjusted_close,
    volume = EXCLUDED.volume,
    source = EXCLUDED.source,
    ingestion_timestamp = CURRENT_TIMESTAMP;
"""


rows = df.select([
    "trade_date",
    "symbol",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
]).rows()

data = [
    (
        row[0],   # trade_date
        row[1],   # symbol
        row[2],   # exchange
        row[3],   # open
        row[4],   # high
        row[5],   # low
        row[6],   # close
        row[7],   # adjusted_close
        row[8],   # volume
        "Yahoo Finance",
    )
    for row in rows
]


# ============================================================
# EXECUTE LOAD
# ============================================================

print(f"\nLoading {len(data):,} rows...")

try:
    cursor.executemany(insert_sql, data)

    conn.commit()

    print("PostgreSQL transaction: COMMITTED")

except Exception:
    conn.rollback()
    print("PostgreSQL transaction: ROLLED BACK")
    raise

finally:
    cursor.close()
    conn.close()


# ============================================================
# COMPLETION
# ============================================================

print("\n" + "=" * 70)
print("MARKET DATA LOAD COMPLETED")
print("=" * 70)

print(f"Rows processed : {len(data):,}")
print(f"Symbols        : {df.select('symbol').n_unique()}")
print(
    f"Date range     : {df['trade_date'].min()} "
    f"to {df['trade_date'].max()}"
)

print("=" * 70)
