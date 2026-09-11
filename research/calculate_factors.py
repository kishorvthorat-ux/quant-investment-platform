from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = PROJECT_ROOT / "duckdb" / "analytics.duckdb"

with duckdb.connect(str(DUCKDB_PATH)) as con:
    con.execute("DROP TABLE IF EXISTS analytics.main.market_factors")

    con.execute("""
        CREATE TABLE analytics.main.market_factors AS
        WITH prices AS (
            SELECT
                trade_date,
                symbol,
                exchange,
                close,
                LAG(close) OVER (
                    PARTITION BY symbol ORDER BY trade_date
                ) AS previous_close
            FROM analytics.main.market_prices
        ),
        returns AS (
            SELECT
                trade_date,
                symbol,
                exchange,
                close,
                close / NULLIF(previous_close, 0) - 1 AS daily_return
            FROM prices
        ),
        factors AS (
            SELECT
                trade_date,
                symbol,
                exchange,
                close,

                close / NULLIF(
                    LAG(close, 20) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                    ), 0
                ) - 1 AS return_20d,

                close / NULLIF(
                    LAG(close, 60) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                    ), 0
                ) - 1 AS return_60d,

                close / NULLIF(
                    LAG(close, 252) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                    ), 0
                ) - 1 AS return_252d,

                close / NULLIF(
                    AVG(close) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ), 0
                ) - 1 AS price_vs_ma_20d,

                close / NULLIF(
                    AVG(close) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                    ), 0
                ) - 1 AS price_vs_ma_60d,

                close / NULLIF(
                    AVG(close) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                    ), 0
                ) - 1 AS price_vs_ma_252d,

                STDDEV_SAMP(daily_return) OVER (
                    PARTITION BY symbol ORDER BY trade_date
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) * SQRT(252) AS volatility_20d,

                STDDEV_SAMP(daily_return) OVER (
                    PARTITION BY symbol ORDER BY trade_date
                    ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                ) * SQRT(252) AS volatility_60d,

                STDDEV_SAMP(daily_return) OVER (
                    PARTITION BY symbol ORDER BY trade_date
                    ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                ) * SQRT(252) AS volatility_252d,

                close / NULLIF(
                    MAX(close) OVER (
                        PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                    ), 0
                ) - 1 AS drawdown_252d

            FROM returns
        )
        SELECT *
        FROM factors
        ORDER BY trade_date, symbol
    """)

    result = con.execute("""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT symbol) AS symbols,
            MIN(trade_date) AS min_date,
            MAX(trade_date) AS max_date,
            COUNT(*) FILTER (WHERE return_252d IS NOT NULL) AS momentum_ready_rows
        FROM analytics.main.market_factors
    """).fetchone()

print(
    f"Factor dataset created: rows={result[0]}, symbols={result[1]}, "
    f"min_date={result[2]}, max_date={result[3]}, "
    f"momentum_ready_rows={result[4]}"
)
