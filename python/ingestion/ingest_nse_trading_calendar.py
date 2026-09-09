import os
from datetime import date, time
from pathlib import Path

import polars as pl
import psycopg2
from dotenv import load_dotenv


# ============================================================
# NSE OFFICIAL TRADING CALENDAR INGESTION
# ============================================================
#
# Purpose:
#   Populate metadata.trading_calendar with the authoritative
#   NSE Equity / Capital Market trading calendar.
#
# Calendar coverage:
#   2020-2026
#
# Important:
#   This is separate from the provisional Yahoo-observed calendar:
#
#       build_trading_calendar.py
#
#   Yahoo remains the market-price source.
#   NSE remains the trading-calendar source.
#
# Target:
#   metadata.trading_calendar
#
# Contract:
#   calendar_id      = NSE_OFFICIAL
#   market_id        = NSE_INDIA
#   source           = NSE
#
# ============================================================


load_dotenv(dotenv_path=".env")


CALENDAR_ID = "NSE_OFFICIAL"
MARKET_ID = "NSE_INDIA"
SOURCE = "NSE"

START_YEAR = 2020
END_YEAR = 2026

NORMAL_SESSION_OPEN = time(9, 15)
NORMAL_SESSION_CLOSE = time(15, 30)


# ----------------------------------------------------------------
# Official NSE Equity / Capital Market holidays.
#
# Weekend holidays are retained for auditability even though the
# normal calendar logic already treats Saturday/Sunday as closed.
#
# Sources:
#   NSE Capital Market annual holiday circulars, 2020-2025
#   NSE official holiday page / 2026 Capital Market calendar
#
# ----------------------------------------------------------------

NSE_HOLIDAYS = {

    2020: {
        "2020-01-26": "Republic Day",
        "2020-02-21": "Mahashivratri",
        "2020-03-10": "Holi",
        "2020-04-02": "Ram Navami",
        "2020-04-06": "Mahavir Jayanti",
        "2020-04-10": "Good Friday",
        "2020-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2020-05-01": "Maharashtra Day",
        "2020-05-25": "Id-Ul-Fitr (Ramzan ID)",
        "2020-08-01": "Bakri Id",
        "2020-08-15": "Independence Day",
        "2020-08-22": "Ganesh Chaturthi",
        "2020-08-30": "Moharram",
        "2020-10-02": "Mahatma Gandhi Jayanti",
        "2020-10-25": "Dasera",
        "2020-11-14": "Diwali-Laxmi Pujan",
        "2020-11-16": "Diwali-Balipratipada",
        "2020-11-30": "Gurunanak Jayanti",
        "2020-12-25": "Christmas",
    },

    2021: {
        "2021-01-26": "Republic Day",
        "2021-03-11": "Mahashivratri",
        "2021-03-29": "Holi",
        "2021-04-02": "Good Friday",
        "2021-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2021-04-21": "Ram Navami",
        "2021-04-25": "Mahavir Jayanti",
        "2021-05-01": "Maharashtra Day",
        "2021-05-13": "Id-Ul-Fitr (Ramzan ID)",
        "2021-07-21": "Bakri Id",
        "2021-08-15": "Independence Day",
        "2021-08-19": "Moharram",
        "2021-09-10": "Ganesh Chaturthi",
        "2021-10-02": "Mahatma Gandhi Jayanti",
        "2021-10-15": "Dussehra",
        "2021-11-04": "Diwali-Laxmi Pujan",
        "2021-11-05": "Diwali-Balipratipada",
        "2021-11-19": "Gurunanak Jayanti",
        "2021-12-25": "Christmas",
    },

    2022: {
        "2022-01-26": "Republic Day",
        "2022-03-01": "Mahashivratri",
        "2022-03-18": "Holi",
        "2022-04-10": "Ram Navami",
        "2022-04-14": "Dr. Baba Saheb Ambedkar Jayanti / Mahavir Jayanti",
        "2022-04-15": "Good Friday",
        "2022-05-01": "Maharashtra Day",
        "2022-05-03": "Id-Ul-Fitr (Ramzan ID)",
        "2022-07-10": "Bakri Id",
        "2022-08-09": "Moharram",
        "2022-08-15": "Independence Day",
        "2022-08-31": "Ganesh Chaturthi",
        "2022-10-02": "Mahatma Gandhi Jayanti",
        "2022-10-05": "Dussehra",
        "2022-10-24": "Diwali-Laxmi Pujan",
        "2022-10-26": "Diwali-Balipratipada",
        "2022-11-08": "Gurunanak Jayanti",
        "2022-12-25": "Christmas",
    },

    2023: {
        "2023-01-26": "Republic Day",
        "2023-02-18": "Mahashivratri",
        "2023-03-07": "Holi",
        "2023-03-30": "Ram Navami",
        "2023-04-04": "Mahavir Jayanti",
        "2023-04-07": "Good Friday",
        "2023-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2023-04-22": "Id-Ul-Fitr (Ramzan ID)",
        "2023-05-01": "Maharashtra Day",
        "2023-06-28": "Bakri Id",
        "2023-07-29": "Moharram",
        "2023-08-15": "Independence Day",
        "2023-09-19": "Ganesh Chaturthi",
        "2023-10-02": "Mahatma Gandhi Jayanti",
        "2023-10-24": "Dussehra",
        "2023-11-12": "Diwali-Laxmi Pujan",
        "2023-11-14": "Diwali-Balipratipada",
        "2023-11-27": "Gurunanak Jayanti",
        "2023-12-25": "Christmas",
    },

    2024: {
        "2024-01-22": "Public Holiday - Ram Temple Consecration",
        "2024-01-26": "Republic Day",
        "2024-03-08": "Mahashivratri",
        "2024-03-25": "Holi",
        "2024-03-29": "Good Friday",
        "2024-04-11": "Id-Ul-Fitr (Ramadan Eid)",
        "2024-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2024-04-17": "Shri Ram Navmi",
        "2024-04-21": "Shri Mahavir Jayanti",
        "2024-05-01": "Maharashtra Day",
        "2024-06-17": "Bakri Id",
        "2024-07-17": "Moharram",
        "2024-08-15": "Independence Day / Parsi New Year",
        "2024-09-07": "Ganesh Chaturthi",
        "2024-10-02": "Mahatma Gandhi Jayanti",
        "2024-10-12": "Dussehra",
        "2024-11-01": "Diwali Laxmi Pujan",
        "2024-11-02": "Diwali-Balipratipada",
        "2024-11-15": "Gurunanak Jayanti",
        "2024-11-20": "Maharashtra Assembly Election",
        "2024-12-25": "Christmas",
    },

    2025: {
        "2025-02-26": "Mahashivratri",
        "2025-03-14": "Holi",
        "2025-03-31": "Id-Ul-Fitr (Ramadan Eid)",
        "2025-04-10": "Shri Mahavir Jayanti",
        "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
        "2025-04-18": "Good Friday",
        "2025-05-01": "Maharashtra Day",
        "2025-08-15": "Independence Day",
        "2025-08-27": "Ganesh Chaturthi",
        "2025-10-02": "Mahatma Gandhi Jayanti / Dussehra",
        "2025-10-21": "Diwali Laxmi Pujan",
        "2025-10-22": "Diwali-Balipratipada",
        "2025-11-05": "Prakash Gurpurb Sri Guru Nanak Dev",
        "2025-12-25": "Christmas",
    },

    2026: {
        "2026-01-15": "Municipal Corporation Election in Maharashtra",
        "2026-01-26": "Republic Day",
        "2026-02-19": "Chhatrapati Shivaji Maharaj Jayanti",
        "2026-03-03": "Holi (Second Day)",
        "2026-03-19": "Gudhi Padwa",
        "2026-03-26": "Ram Navami",
        "2026-03-31": "Mahavir Jayanti",
        "2026-04-01": "Annual Bank Closing",
        "2026-04-03": "Good Friday",
        "2026-04-14": "Dr. Babasaheb Ambedkar Jayanti",
        "2026-05-01": "Maharashtra Din / Buddha Pournima",
        "2026-05-28": "Bakri ID (Id-Uz-Zuha)",
        "2026-06-26": "Muharram",
        "2026-08-26": "Id-E-Milad",
        "2026-09-14": "Ganesh Chaturthi",
        "2026-10-02": "Mahatma Gandhi Jayanti",
        "2026-10-20": "Dussehra",
        "2026-11-08": "Diwali Laxmi Pujan - Muhurat Trading",
        "2026-11-10": "Diwali (Bali Pratipada)",
        "2026-11-24": "Guru Nanak Jayanti",
        "2026-12-25": "Christmas",
    },
}


# ----------------------------------------------------------------
# Exceptional trading dates.
#
# 2024-01-20 was a Saturday on which NSE conducted a regular
# equity/equity-derivatives trading session from the primary site.
#
# It must therefore override the normal weekend rule.
# ----------------------------------------------------------------

SPECIAL_TRADING_DATES = {
    "2024-01-20": "Special live trading session",
}


# ----------------------------------------------------------------
# Database configuration
# ----------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5434")),
    "database": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


def build_holiday_dataframe() -> pl.DataFrame:
    """Build one normalized holiday dataframe for all configured years."""

    rows = []

    for year, holidays in NSE_HOLIDAYS.items():
        for trade_date, holiday_name in holidays.items():
            rows.append(
                {
                    "trade_date": date.fromisoformat(trade_date),
                    "holiday_name": holiday_name,
                }
            )

    return pl.DataFrame(rows)


def build_calendar() -> pl.DataFrame:
    """
    Build the NSE official calendar for 2020-2026.

    Weekends are represented explicitly as non-trading days.

    Official NSE holidays are represented as non-trading days.

    Exceptional NSE trading dates override the normal weekend rule.
    """

    start_date = date(START_YEAR, 1, 1)
    end_date = date(END_YEAR, 12, 31)

    dates = pl.date_range(
        start=start_date,
        end=end_date,
        interval="1d",
        eager=True,
    )

    holiday_df = build_holiday_dataframe()

    special_trading = {
        date.fromisoformat(trade_date): description
        for trade_date, description in SPECIAL_TRADING_DATES.items()
    }

    special_trading_df = pl.DataFrame(
        {
            "trade_date": list(special_trading.keys()),
            "special_name": list(special_trading.values()),
        }
    )

    calendar = (
        pl.DataFrame({"trade_date": dates})
        .with_columns(
            pl.col("trade_date").dt.weekday().alias("weekday")
        )
        .join(
            holiday_df,
            on="trade_date",
            how="left",
        )
        .join(
            special_trading_df,
            on="trade_date",
            how="left",
        )
        .with_columns(
            (
                (
                    (pl.col("weekday") <= 5)
                    & pl.col("holiday_name").is_null()
                )
                | pl.col("special_name").is_not_null()
            ).alias("is_trading_day"),

            pl.when(pl.col("special_name").is_not_null())
            .then(pl.col("special_name"))
            .otherwise(pl.col("holiday_name"))
            .alias("holiday_name"),

            pl.col("trade_date")
            .dt.year()
            .cast(pl.String)
            .alias("calendar_version"),

            pl.lit(CALENDAR_ID).alias("calendar_id"),
            pl.lit(MARKET_ID).alias("market_id"),
            pl.lit(SOURCE).alias("source"),
        )
        .with_columns(
            pl.when(pl.col("is_trading_day"))
            .then(pl.lit(NORMAL_SESSION_OPEN))
            .otherwise(pl.lit(None, dtype=pl.Time))
            .alias("session_open"),

            pl.when(pl.col("is_trading_day"))
            .then(pl.lit(NORMAL_SESSION_CLOSE))
            .otherwise(pl.lit(None, dtype=pl.Time))
            .alias("session_close"),
        )
        .select(
            [
                "calendar_id",
                "market_id",
                "trade_date",
                "is_trading_day",
                "session_open",
                "session_close",
                "holiday_name",
                "source",
                "calendar_version",
            ]
        )
        .sort("trade_date")
    )

    return calendar


def validate_calendar(df: pl.DataFrame) -> None:
    """Run structural validation before database loading."""

    if df.is_empty():
        raise ValueError("Calendar is empty.")

    expected_days = sum(
        366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        else 365
        for year in range(START_YEAR, END_YEAR + 1)
    )

    if df.height != expected_days:
        raise ValueError(
            f"Expected {expected_days} calendar days for "
            f"{START_YEAR}-{END_YEAR}, got {df.height}."
        )

    duplicate_count = (
        df.group_by(["calendar_id", "trade_date"])
        .len()
        .filter(pl.col("len") > 1)
        .height
    )

    if duplicate_count:
        raise ValueError(
            f"Found {duplicate_count} duplicate calendar keys."
        )

    required_columns = [
        "calendar_id",
        "market_id",
        "trade_date",
        "is_trading_day",
        "source",
        "calendar_version",
    ]

    for column in required_columns:
        if df.filter(pl.col(column).is_null()).height > 0:
            raise ValueError(
                f"Required column contains NULL values: {column}"
            )

    expected_years = list(range(START_YEAR, END_YEAR + 1))

    actual_years = (
        df.select(pl.col("trade_date").dt.year().unique())
        .to_series()
        .sort()
        .to_list()
    )

    if actual_years != expected_years:
        raise ValueError(
            f"Unexpected calendar years. "
            f"Expected {expected_years}, got {actual_years}."
        )

    invalid_versions = df.filter(
        pl.col("calendar_version")
        != pl.col("trade_date").dt.year().cast(pl.String)
    )

    if invalid_versions.height > 0:
        raise ValueError(
            "calendar_version does not match trade_date year."
        )

    trading_rows = df.filter(pl.col("is_trading_day"))

    if trading_rows.filter(
        pl.col("session_open").is_null()
        | pl.col("session_close").is_null()
    ).height > 0:
        raise ValueError(
            "Trading days must have session_open and session_close."
        )

    non_trading_rows = df.filter(~pl.col("is_trading_day"))

    if non_trading_rows.filter(
        pl.col("session_open").is_not_null()
        | pl.col("session_close").is_not_null()
    ).height > 0:
        raise ValueError(
            "Non-trading days must not have normal session times."
        )

    special_trading_date = date(2024, 1, 20)

    special_check = df.filter(
        pl.col("trade_date") == special_trading_date
    )

    if special_check.height != 1:
        raise ValueError(
            "2024-01-20 special trading date is missing."
        )

    if not special_check["is_trading_day"][0]:
        raise ValueError(
            "2024-01-20 must be marked as a trading day."
        )

    print("Calendar validation: PASS")


def load_calendar(df: pl.DataFrame) -> None:
    """Upsert the validated calendar into metadata.trading_calendar."""

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cur:
            for row in df.iter_rows(named=True):
                cur.execute(
                    """
                    INSERT INTO metadata.trading_calendar (
                        calendar_id,
                        market_id,
                        trade_date,
                        is_trading_day,
                        session_open,
                        session_close,
                        holiday_name,
                        source,
                        calendar_version
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (calendar_id, trade_date)
                    DO UPDATE SET
                        market_id = EXCLUDED.market_id,
                        is_trading_day = EXCLUDED.is_trading_day,
                        session_open = EXCLUDED.session_open,
                        session_close = EXCLUDED.session_close,
                        holiday_name = EXCLUDED.holiday_name,
                        source = EXCLUDED.source,
                        calendar_version = EXCLUDED.calendar_version
                    """,
                    (
                        row["calendar_id"],
                        row["market_id"],
                        row["trade_date"],
                        row["is_trading_day"],
                        row["session_open"],
                        row["session_close"],
                        row["holiday_name"],
                        row["source"],
                        row["calendar_version"],
                    ),
                )

        conn.commit()

    finally:
        conn.close()


def main() -> None:
    print("=" * 60)
    print("NSE Official Trading Calendar Ingestion")
    print("=" * 60)

    calendar = build_calendar()

    print(f"Calendar ID : {CALENDAR_ID}")
    print(f"Market ID   : {MARKET_ID}")
    print(f"Source      : {SOURCE}")
    print(f"Version     : {START_YEAR}-{END_YEAR}")
    print(f"Rows        : {calendar.height:,}")
    print(
        f"Date range  : "
        f"{calendar['trade_date'].min()} → "
        f"{calendar['trade_date'].max()}"
    )

    trading_days = calendar.filter(
        pl.col("is_trading_day")
    ).height

    non_trading_days = calendar.filter(
        ~pl.col("is_trading_day")
    ).height

    print(f"Trading days     : {trading_days:,}")
    print(f"Non-trading days : {non_trading_days:,}")

    print()
    print("Trading days by year:")

    yearly = (
        calendar
        .group_by("calendar_version")
        .agg(
            pl.len().alias("calendar_days"),
            pl.col("is_trading_day")
            .sum()
            .alias("trading_days"),
        )
        .sort("calendar_version")
    )

    print(yearly)

    validate_calendar(calendar)

    load_calendar(calendar)

    print("Database load: PASS")
    print("NSE official calendar ingestion completed.")


if __name__ == "__main__":
    main()
