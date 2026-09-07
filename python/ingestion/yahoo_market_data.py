import os
from pathlib import Path

import polars as pl
import yfinance as yf
import psycopg2
from dotenv import load_dotenv


# ============================================================
# 1. LOAD ENVIRONMENT
# ============================================================

load_dotenv(dotenv_path=".env")


# ============================================================
# 2. CONFIGURATION
# ============================================================

START_DATE = "2020-01-01"

SOURCE_ID = "YAHOO_FINANCE"

OUTPUT_DIR = Path("data/raw/market")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "yahoo_equities.parquet"


# ============================================================
# 3. POSTGRES CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5434")),
    "database": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


# ============================================================
# 4. LOAD ACTIVE SECURITIES + SOURCE MAPPINGS
# ============================================================

print()
print("=" * 70)
print("LOADING SECURITY UNIVERSE")
print("=" * 70)

conn = psycopg2.connect(**DB_CONFIG)

try:

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                s.security_id,
                s.symbol,
                m.source_symbol AS yahoo_symbol,
                mm.exchange_code AS exchange
            FROM metadata.security_master s
            JOIN metadata.security_source_mapping m
              ON m.security_id = s.security_id
            JOIN metadata.market_master mm
              ON mm.market_id = s.market_id
            WHERE s.active_flag = TRUE
              AND m.source_id = %s
              AND m.active_flag = TRUE
              AND m.valid_from <= CURRENT_DATE
              AND (
                    m.valid_to IS NULL
                    OR m.valid_to >= CURRENT_DATE
                  )
            ORDER BY s.security_id
            """,
            (SOURCE_ID,),
        )

        securities = cur.fetchall()

finally:
    conn.close()


if not securities:

    raise RuntimeError(
        "No active securities with valid Yahoo Finance mappings found."
    )


print(
    f"Active securities with Yahoo mappings: {len(securities)}"
)


# ============================================================
# 5. VALIDATE SECURITY MAPPINGS
# ============================================================

missing_mapping = []

for (
    security_id,
    symbol,
    yahoo_symbol,
    exchange
) in securities:

    if not yahoo_symbol:

        missing_mapping.append(
            (
                security_id,
                symbol,
            )
        )


if missing_mapping:

    print()
    print("ERROR: Missing Yahoo Finance mappings:")

    for security_id, symbol in missing_mapping:

        print(
            f"{security_id:3} | {symbol}"
        )

    raise RuntimeError(
        "Active securities are missing Yahoo Finance mappings."
    )


# ============================================================
# 6. DISPLAY UNIVERSE
# ============================================================

print()
print("Security → Yahoo mapping")
print("-" * 70)

for (
    security_id,
    symbol,
    yahoo_symbol,
    exchange
) in securities:

    print(
        f"{security_id:3} | "
        f"{symbol:15} | "
        f"{yahoo_symbol}"
    )

print("-" * 70)


# ============================================================
# 7. BUILD TICKER LIST
# ============================================================

TICKERS = [
    yahoo_symbol
    for (
        security_id,
        symbol,
        yahoo_symbol,
        exchange
    ) in securities
]


print()
print(
    f"Tickers to download: {len(TICKERS)}"
)

print(
    f"Start date:           {START_DATE}"
)


# ============================================================
# 8. DOWNLOAD
# ============================================================

print()
print("=" * 70)
print("DOWNLOADING MARKET DATA")
print("=" * 70)

df = yf.download(
    TICKERS,
    start=START_DATE,
    interval="1d",
    auto_adjust=False,
    actions=True,
    group_by="ticker",
    progress=True,
    threads=True,
)


# ============================================================
# 9. CHECK DOWNLOAD
# ============================================================

if df is None or df.empty:

    raise RuntimeError(
        "Yahoo Finance returned no data."
    )


# ============================================================
# 10. IDENTIFY RETURNED TICKERS
# ============================================================

if hasattr(df.columns, "get_level_values"):

    returned_tickers = set(
        df.columns.get_level_values(0)
    )

else:

    returned_tickers = set()


# ============================================================
# 11. PROCESS EACH SECURITY
# ============================================================

records = []

successful_symbols = []

failed_symbols = []


for (
    security_id,
    symbol,
    yahoo_symbol,
    exchange
) in securities:

    print()
    print(
        f"Processing "
        f"{symbol} "
        f"({yahoo_symbol})..."
    )


    # --------------------------------------------------------
    # Check ticker existence
    # --------------------------------------------------------

    if yahoo_symbol not in returned_tickers:

        print(
            "  FAILED: ticker not returned by Yahoo."
        )

        failed_symbols.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "reason": "ticker_not_returned",
            }
        )

        continue


    # --------------------------------------------------------
    # Extract ticker
    # --------------------------------------------------------

    try:

        ticker_df = df[yahoo_symbol].copy()

    except Exception as exc:

        print(
            f"  FAILED: extraction error: {exc}"
        )

        failed_symbols.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "reason": "extraction_error",
            }
        )

        continue


    # --------------------------------------------------------
    # Reset date index
    # --------------------------------------------------------

    ticker_df = ticker_df.reset_index()


    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required_columns = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    ]


    missing_columns = [
        column
        for column in required_columns
        if column not in ticker_df.columns
    ]


    if missing_columns:

        print(
            f"  FAILED: missing columns "
            f"{missing_columns}"
        )

        failed_symbols.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "reason": (
                    f"missing_columns:{missing_columns}"
                ),
            }
        )

        continue


    # --------------------------------------------------------
    # IMPORTANT:
    # Check actual price data, not just row count
    # --------------------------------------------------------

    usable_price_rows = (
        ticker_df["Close"]
        .notna()
        .sum()
    )


    if usable_price_rows == 0:

        print(
            "  FAILED: no usable price data."
        )

        failed_symbols.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "reason": "zero_usable_price_rows",
            }
        )

        continue


    # --------------------------------------------------------
    # Remove rows without Close price
    # --------------------------------------------------------

    ticker_df = ticker_df[
        ticker_df["Close"].notna()
    ].copy()


    if ticker_df.empty:

        print(
            "  FAILED: dataframe empty after "
            "removing invalid rows."
        )

        failed_symbols.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "reason": "empty_after_filter",
            }
        )

        continue


    # --------------------------------------------------------
    # Rename columns
    # --------------------------------------------------------

    ticker_df = ticker_df.rename(
        columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adjusted_close",
            "Volume": "volume",
        }
    )


    # --------------------------------------------------------
    # Add canonical security metadata
    # --------------------------------------------------------

    ticker_df["security_id"] = security_id

    ticker_df["symbol"] = symbol

    ticker_df["exchange"] = exchange


    # --------------------------------------------------------
    # Keep ONLY standard columns
    #
    # This guarantees every dataframe has the same schema
    # before Polars concatenation.
    # --------------------------------------------------------

    ticker_df = ticker_df[
        [
            "trade_date",
            "security_id",
            "symbol",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
        ]
    ]


    # --------------------------------------------------------
    # Add to records
    # --------------------------------------------------------

    records.append(ticker_df)

    successful_symbols.append(symbol)


    print(
        f"  OK: {len(ticker_df):,} usable rows"
    )


# ============================================================
# 12. DOWNLOAD SUMMARY
# ============================================================

print()
print("=" * 70)
print("DOWNLOAD SUMMARY")
print("=" * 70)

print(
    f"Requested securities : {len(securities)}"
)

print(
    f"Successful securities: {len(successful_symbols)}"
)

print(
    f"Failed securities    : {len(failed_symbols)}"
)


if failed_symbols:

    print()
    print("Failed securities")
    print("-" * 70)

    for item in failed_symbols:

        print(
            f"{item['symbol']:15} | "
            f"{item['yahoo_symbol']:20} | "
            f"{item['reason']}"
        )


print("=" * 70)


# ============================================================
# 13. FAIL ONLY IF EVERYTHING FAILED
# ============================================================

if not records:

    raise RuntimeError(
        "No securities produced usable market data."
    )


# ============================================================
# 14. CONVERT EACH FRAME TO A STANDARD POLARS SCHEMA
# ============================================================

print()
print("Converting data to Polars...")


polars_frames = []


for pandas_df in records:

    frame = pl.from_pandas(
        pandas_df
    )


    # --------------------------------------------------------
    # Force a consistent schema
    # --------------------------------------------------------

    frame = frame.select(
        [
            "trade_date",
            "security_id",
            "symbol",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
        ]
    )


    frame = frame.with_columns(
        [
            pl.col("trade_date")
            .cast(pl.Date),

            pl.col("security_id")
            .cast(pl.Int64),

            pl.col("symbol")
            .cast(pl.Utf8),

            pl.col("exchange")
            .cast(pl.Utf8),

            pl.col("open")
            .cast(pl.Float64),

            pl.col("high")
            .cast(pl.Float64),

            pl.col("low")
            .cast(pl.Float64),

            pl.col("close")
            .cast(pl.Float64),

            pl.col("adjusted_close")
            .cast(pl.Float64),

            pl.col("volume")
            .cast(pl.Int64),
        ]
    )


    polars_frames.append(frame)


# ============================================================
# 15. COMBINE
# ============================================================

combined = pl.concat(
    polars_frames,
    how="vertical",
)


# ============================================================
# 16. SORT
# ============================================================

combined = combined.sort(
    [
        "symbol",
        "trade_date",
    ]
)


# ============================================================
# 17. BASIC DATA QUALITY VALIDATION
# ============================================================

print()
print("=" * 70)
print("DATA QUALITY VALIDATION")
print("=" * 70)


row_count = combined.height

security_count = (
    combined
    .select(
        pl.col("security_id")
        .n_unique()
    )
    .item()
)

symbol_count = (
    combined
    .select(
        pl.col("symbol")
        .n_unique()
    )
    .item()
)

duplicate_count = (
    combined
    .group_by(
        [
            "trade_date",
            "security_id",
        ]
    )
    .len()
    .filter(
        pl.col("len") > 1
    )
    .height
)


null_close_count = (
    combined
    .select(
        pl.col("close")
        .is_null()
        .sum()
    )
    .item()
)


invalid_price_count = (
    combined
    .filter(
        (pl.col("open") <= 0)
        | (pl.col("high") <= 0)
        | (pl.col("low") <= 0)
        | (pl.col("close") <= 0)
    )
    .height
)


print(
    f"Total rows          : {row_count:,}"
)

print(
    f"Distinct securities  : {security_count}"
)

print(
    f"Distinct symbols     : {symbol_count}"
)

print(
    f"Duplicate rows       : {duplicate_count:,}"
)

print(
    f"Null close prices    : {null_close_count:,}"
)

print(
    f"Invalid price rows   : {invalid_price_count:,}"
)


if duplicate_count > 0:

    raise RuntimeError(
        "Duplicate trade_date/security_id rows detected."
    )


if null_close_count > 0:

    raise RuntimeError(
        "Null close prices detected after filtering."
    )


if invalid_price_count > 0:

    raise RuntimeError(
        "Invalid non-positive price values detected."
    )


# ============================================================
# 18. FINAL DATA SUMMARY
# ============================================================

print()
print("=" * 70)
print("FINAL DATASET")
print("=" * 70)

print(
    f"Rows                : {combined.height:,}"
)

print(
    f"Columns             : {combined.width}"
)

print(
    f"Date range          : "
    f"{combined['trade_date'].min()} "
    f"to "
    f"{combined['trade_date'].max()}"
)

print(
    f"Securities           : {security_count}"
)

print(
    f"Successful securities: {len(successful_symbols)}"
)

print(
    f"Failed securities    : {len(failed_symbols)}"
)


# ============================================================
# 19. WRITE PARQUET
# ============================================================

print()
print("=" * 70)
print("WRITING PARQUET")
print("=" * 70)

combined.write_parquet(
    OUTPUT_FILE
)


print(
    f"Output file: {OUTPUT_FILE}"
)


# ============================================================
# 20. FINAL CONFIRMATION
# ============================================================

print()
print("=" * 70)
print("INGESTION COMPLETE")
print("=" * 70)

print(
    f"File      : {OUTPUT_FILE}"
)

print(
    f"Rows      : {combined.height:,}"
)

print(
    f"Securities: {security_count}"
)

print(
    f"Failures  : {len(failed_symbols)}"
)

print("=" * 70)
