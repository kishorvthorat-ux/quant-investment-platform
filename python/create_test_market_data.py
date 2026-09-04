import polars as pl
from pathlib import Path


output_path = Path("data/raw/market/test_prices.parquet")

data = {
    "trade_date": [
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ],
    "symbol": [
        "RELIANCE",
        "RELIANCE",
        "RELIANCE",
        "RELIANCE",
    ],
    "exchange": [
        "NSE",
        "NSE",
        "NSE",
        "NSE",
    ],
    "open": [
        1400.0,
        1410.0,
        1420.0,
        1430.0,
    ],
    "high": [
        1420.0,
        1430.0,
        1440.0,
        1450.0,
    ],
    "low": [
        1390.0,
        1400.0,
        1410.0,
        1420.0,
    ],
    "close": [
        1415.0,
        1425.0,
        1435.0,
        1445.0,
    ],
    "volume": [
        1000000,
        1100000,
        1200000,
        1300000,
    ],
}

df = pl.DataFrame(data)

df = df.with_columns(
    pl.col("trade_date").str.to_date()
)

output_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

df.write_parquet(output_path)

print(f"Created: {output_path}")
print(f"Rows: {df.height}")
print(df)
