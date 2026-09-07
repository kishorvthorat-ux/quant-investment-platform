with returns as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        open,
        high,
        low,
        close,
        adjusted_close,
        volume,
        daily_return,
        previous_adjusted_close

    from {{ ref('daily_returns') }}

),

base_features as (

    select
        *,

        -- ============================================================
        -- Existing momentum features
        -- ============================================================

        adjusted_close /
            lag(adjusted_close, 20) over (
                partition by security_id
                order by trade_date
            ) - 1
            as return_20d,

        adjusted_close /
            lag(adjusted_close, 60) over (
                partition by security_id
                order by trade_date
            ) - 1
            as return_60d,

        adjusted_close /
            lag(adjusted_close, 252) over (
                partition by security_id
                order by trade_date
            ) - 1
            as return_252d,


        -- ============================================================
        -- Existing moving averages
        -- ============================================================

        avg(adjusted_close) over (
            partition by security_id
            order by trade_date
            rows between 19 preceding and current row
        ) as moving_avg_20d,

        avg(adjusted_close) over (
            partition by security_id
            order by trade_date
            rows between 59 preceding and current row
        ) as moving_avg_60d,

        avg(adjusted_close) over (
            partition by security_id
            order by trade_date
            rows between 251 preceding and current row
        ) as moving_avg_252d,


        -- ============================================================
        -- Existing volatility features
        -- ============================================================

        stddev_samp(daily_return) over (
            partition by security_id
            order by trade_date
            rows between 19 preceding and current row
        ) * sqrt(252) as volatility_20d,

        stddev_samp(daily_return) over (
            partition by security_id
            order by trade_date
            rows between 59 preceding and current row
        ) * sqrt(252) as volatility_60d,

        stddev_samp(daily_return) over (
            partition by security_id
            order by trade_date
            rows between 251 preceding and current row
        ) * sqrt(252) as volatility_252d,


        -- ============================================================
        -- Existing all-time running maximum
        -- ============================================================

        max(adjusted_close) over (
            partition by security_id
            order by trade_date
            rows between unbounded preceding and current row
        ) as running_max_price,


        -- ============================================================
        -- Adjusted OHLC
        --
        -- Yahoo provides adjusted_close separately from raw OHLC.
        -- We scale OHLC using adjusted_close / close so ATR is
        -- calculated on the same price basis as the rest of the
        -- quantitative feature framework.
        -- ============================================================

        high * (adjusted_close / nullif(close, 0))
            as adjusted_high,

        low * (adjusted_close / nullif(close, 0))
            as adjusted_low,


        -- ============================================================
        -- True Range on adjusted price basis
        -- ============================================================

        greatest(
            high * (adjusted_close / nullif(close, 0))
                - low * (adjusted_close / nullif(close, 0)),

            abs(
                high * (adjusted_close / nullif(close, 0))
                    - previous_adjusted_close
            ),

            abs(
                low * (adjusted_close / nullif(close, 0))
                    - previous_adjusted_close
            )
        ) as true_range,


        -- ============================================================
        -- Rolling 252-day high
        -- ============================================================

        max(adjusted_close) over (
            partition by security_id
            order by trade_date
            rows between 251 preceding and current row
        ) as rolling_max_price_252d,


        -- ============================================================
        -- RSI components
        -- ============================================================

        case
            when daily_return > 0 then daily_return
            else 0
        end as gain,

        case
            when daily_return < 0 then abs(daily_return)
            else 0
        end as loss

    from returns

),

rsi_features as (

    select
        *,

        avg(gain) over (
            partition by security_id
            order by trade_date
            rows between 13 preceding and current row
        ) as avg_gain_14d,

        avg(loss) over (
            partition by security_id
            order by trade_date
            rows between 13 preceding and current row
        ) as avg_loss_14d

    from base_features

),

final_features as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,

        adjusted_close,
        daily_return,

        -- Existing features

        return_20d,
        return_60d,
        return_252d,

        moving_avg_20d,
        moving_avg_60d,
        moving_avg_252d,

        adjusted_close / moving_avg_20d - 1
            as price_vs_ma20,

        adjusted_close / moving_avg_60d - 1
            as price_vs_ma60,

        adjusted_close / moving_avg_252d - 1
            as price_vs_ma252,

        volatility_20d,
        volatility_60d,
        volatility_252d,

        running_max_price,

        adjusted_close / running_max_price - 1
            as drawdown,


        -- New: ATR 14D

        avg(true_range) over (
            partition by security_id
            order by trade_date
            rows between 13 preceding and current row
        ) as atr_14d,


        -- New: ATR percentage

        avg(true_range) over (
            partition by security_id
            order by trade_date
            rows between 13 preceding and current row
        )
        / nullif(adjusted_close, 0)
            as atr_percent_14d,


        -- New: RSI 14D

        case
            when avg_loss_14d = 0
                 and avg_gain_14d > 0
                then 100

            when avg_loss_14d = 0
                then 50

            else
                100
                - (
                    100
                    / (
                        1
                        + (
                            avg_gain_14d
                            / nullif(avg_loss_14d, 0)
                        )
                    )
                )
        end as rsi_14d,


        -- New: rolling 252-day drawdown
        --
        -- Different from the existing all-time drawdown.

        adjusted_close
            / nullif(rolling_max_price_252d, 0)
            - 1
            as drawdown_252d

    from rsi_features

)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    adjusted_close,
    daily_return,

    return_20d,
    return_60d,
    return_252d,

    moving_avg_20d,
    moving_avg_60d,
    moving_avg_252d,

    price_vs_ma20,
    price_vs_ma60,
    price_vs_ma252,

    volatility_20d,
    volatility_60d,
    volatility_252d,

    running_max_price,
    drawdown,

    atr_14d,
    atr_percent_14d,
    rsi_14d,
    drawdown_252d

from final_features
