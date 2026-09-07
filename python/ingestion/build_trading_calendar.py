import polars as pl
from pathlib import Path


INPUT_FILE = Path("data/raw/market/yahoo_equities.parquet")

df = pl.read_parquet(INPUT_FILE)

# Provisional calendar based on dates observed in the market dataset.
# This is NOT an authoritative NSE holiday calendar.
calendar = (
    df
    .select("trade_date")
    .unique()
    .sort("trade_date")
    .with_columns(
        pl.lit("NSE").alias("exchange"),
        pl.lit(True).alias("is_trading_day"),
        pl.lit(None, dtype=pl.Utf8).alias("holiday_name"),
    )
    .select(
        [
            "trade_date",
            "exchange",
            "is_trading_day",
            "holiday_name",
        ]
    )
)

output_file = Path("data/raw/market/trading_calendar.parquet")

calendar.write_parquet(output_file)

print("Provisional Trading calendar created from observed market dates")
print(f"Trading days: {calendar.height:,}")
print(f"First date  : {calendar['trade_date'].min()}")
print(f"Last date   : {calendar['trade_date'].max()}")
print(f"Output      : {output_file}")
