import os
from pathlib import Path
import duckdb
import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = PROJECT_ROOT / "duckdb" / "analytics.duckdb"
TEMP_CSV = PROJECT_ROOT / "duckdb" / "_market_prices.csv"

load_dotenv(PROJECT_ROOT / ".env")

pg_config = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5434"),
    "dbname": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)

with psycopg.connect(**pg_config) as pg:
    with pg.cursor() as cur:
            with open(TEMP_CSV, "w", encoding="utf-8") as f:
                with cur.copy("""COPY (SELECT trade_date, symbol, exchange, open, high, low, close, adjusted_close, volume FROM raw.market_prices ORDER BY trade_date, symbol) TO STDOUT WITH CSV HEADER""") as copy:
                    for data in copy:
                        f.write(bytes(data).decode("utf-8"))

with duckdb.connect(str(DUCKDB_PATH)) as con:
    con.execute("DROP TABLE IF EXISTS analytics.main.market_prices")
    con.execute("""
        CREATE TABLE analytics.main.market_prices AS
        SELECT
            trade_date::DATE AS trade_date,
            symbol::VARCHAR AS symbol,
            exchange::VARCHAR AS exchange,
            open::DOUBLE AS open,
            high::DOUBLE AS high,
            low::DOUBLE AS low,
            close::DOUBLE AS close,
            adjusted_close::DOUBLE AS adjusted_close,
            volume::BIGINT AS volume
        FROM read_csv_auto(?)
    """, [str(TEMP_CSV)])

    result = con.execute("""
        SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(trade_date), MAX(trade_date)
        FROM analytics.main.market_prices
    """).fetchone()

TEMP_CSV.unlink(missing_ok=True)

print(f"DuckDB research dataset refreshed: rows={result[0]}, symbols={result[1]}, min_date={result[2]}, max_date={result[3]}")
