from pathlib import Path
from datetime import datetime

import polars as pl


RAW_PATH = Path("data/raw/market")


def validate_market_data(df: pl.DataFrame) -> pl.DataFrame:

    required_columns = [
        "trade_date",
        "symbol",
        "exchange",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = set(required_columns) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    return df


def save_raw_data(df: pl.DataFrame, dataset_name: str):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output = (
        RAW_PATH /
        f"{dataset_name}_{timestamp}.parquet"
    )

    df.write_parquet(output)

    print(f"Saved: {output}")


def main():

    print("Market data ingestion started")

    # Provider-specific ingestion will be added here.

    print("Market data ingestion completed")


if __name__ == "__main__":
    main()
