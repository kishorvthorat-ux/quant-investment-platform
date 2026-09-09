import os

import psycopg2
from dotenv import load_dotenv


load_dotenv(dotenv_path=".env")


DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5434")),
    "database": os.getenv("POSTGRES_DB", "quant_platform"),
    "user": os.getenv("POSTGRES_USER", "quant_user"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


CALENDAR_ID = "NSE_OFFICIAL"
MARKET_ID = "NSE_INDIA"
EXCHANGE = "NSE"


def main() -> None:
    print("=" * 60)
    print("Load Official NSE Calendar → Raw Compatibility Layer")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cur:

            # ----------------------------------------------------
            # Read authoritative metadata calendar.
            # ----------------------------------------------------
            cur.execute(
                """
                SELECT
                    trade_date,
                    is_trading_day,
                    holiday_name
                FROM metadata.trading_calendar
                WHERE calendar_id = %s
                  AND market_id = %s
                ORDER BY trade_date
                """,
                (CALENDAR_ID, MARKET_ID),
            )

            rows = cur.fetchall()

            if not rows:
                raise ValueError(
                    "No authoritative NSE calendar found in "
                    "metadata.trading_calendar."
                )

            print(f"Source rows       : {len(rows):,}")

            # ----------------------------------------------------
            # Replace raw compatibility calendar atomically within
            # this transaction.
            #
            # raw.trading_calendar is intentionally kept with its
            # existing four-column schema.
            # ----------------------------------------------------
            cur.execute(
                """
                DELETE FROM raw.trading_calendar
                """
            )

            cur.executemany(
                """
                INSERT INTO raw.trading_calendar (
                    trade_date,
                    exchange,
                    is_trading_day,
                    holiday_name
                )
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (
                        trade_date,
                        EXCHANGE,
                        is_trading_day,
                        holiday_name,
                    )
                    for trade_date, is_trading_day, holiday_name in rows
                ],
            )

            # ----------------------------------------------------
            # Validate the compatibility layer before commit.
            # ----------------------------------------------------
            cur.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE is_trading_day),
                    MIN(trade_date),
                    MAX(trade_date)
                FROM raw.trading_calendar
                """
            )

            count, trading_days, min_date, max_date = cur.fetchone()

            if count != len(rows):
                raise ValueError(
                    f"Raw row count mismatch: expected {len(rows)}, "
                    f"got {count}."
                )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM raw.trading_calendar
                WHERE exchange <> %s
                """,
                (EXCHANGE,),
            )

            invalid_exchange_count = cur.fetchone()[0]

            if invalid_exchange_count:
                raise ValueError(
                    f"Found {invalid_exchange_count} rows with "
                    f"unexpected exchange."
                )

        conn.commit()

        print(f"Raw rows         : {count:,}")
        print(f"Trading days     : {trading_days:,}")
        print(f"Non-trading days : {count - trading_days:,}")
        print(f"Date range       : {min_date} → {max_date}")
        print("Compatibility validation: PASS")
        print("Database load: PASS")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
