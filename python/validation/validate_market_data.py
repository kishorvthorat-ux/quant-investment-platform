import polars as pl


FILE = "data/raw/market/yahoo_equities.parquet"

df = pl.read_parquet(FILE)

print("====================================")
print("MARKET DATA QUALITY REPORT")
print("====================================")

print(f"Rows              : {df.height:,}")
print(f"Symbols            : {df['symbol'].n_unique()}")
print(f"Duplicate rows     : {df.is_duplicated().sum()}")

print()
print("Null counts:")

print(
    df.null_count()
)

print()
print("Invalid OHLC rows:")

invalid_ohlc = df.filter(
    (pl.col("high") < pl.col("open"))
    | (pl.col("high") < pl.col("close"))
    | (pl.col("low") > pl.col("open"))
    | (pl.col("low") > pl.col("close"))
    | (pl.col("high") < pl.col("low"))
)

print(f"Invalid OHLC       : {invalid_ohlc.height:,}")

print()
print("Negative volume:")

negative_volume = df.filter(
    pl.col("volume") < 0
)

print(f"Negative volume    : {negative_volume.height:,}")

print()
print("Date range:")

print(
    df.select(
        [
            pl.min("trade_date").alias("min_date"),
            pl.max("trade_date").alias("max_date"),
        ]
    )
)

print()
print("====================================")
