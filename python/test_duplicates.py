import polars as pl

df = pl.DataFrame({
    "trade_date": [
        "2026-09-01",
        "2026-09-01",
        "2026-09-02",
    ],
    "symbol": [
        "RELIANCE",
        "RELIANCE",
        "RELIANCE",
    ],
    "exchange": [
        "NSE",
        "NSE",
        "NSE",
    ],
    "close": [
        1425.0,
        1425.0,
        1435.0,
    ],
})

print("Original data:")
print(df)

duplicates = (
    df
    .group_by(
        ["trade_date", "symbol", "exchange"]
    )
    .agg(
        pl.len().alias("row_count")
    )
    .filter(
        pl.col("row_count") > 1
    )
)

print("\nDuplicates:")
print(duplicates)

df = df.unique(
    subset=[
        "trade_date",
        "symbol",
        "exchange"
    ],
    keep="last"
)

print("\nAfter deduplication:")
print(df)
