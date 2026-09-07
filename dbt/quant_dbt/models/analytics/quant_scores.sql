with base as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,

        return_20d,
        return_60d,
        return_252d,

        price_vs_ma20,
        price_vs_ma60,
        price_vs_ma252,

        volatility_20d,
        volatility_60d,
        volatility_252d,

        drawdown

    from {{ ref('quant_features') }}

),

ranked as (

    select
        *,

        -- Momentum
        percent_rank() over (
            partition by trade_date
            order by return_20d
        ) as rank_return_20d,

        percent_rank() over (
            partition by trade_date
            order by return_60d
        ) as rank_return_60d,

        percent_rank() over (
            partition by trade_date
            order by return_252d
        ) as rank_return_252d,

        -- Trend
        percent_rank() over (
            partition by trade_date
            order by price_vs_ma20
        ) as rank_ma20,

        percent_rank() over (
            partition by trade_date
            order by price_vs_ma60
        ) as rank_ma60,

        percent_rank() over (
            partition by trade_date
            order by price_vs_ma252
        ) as rank_ma252,

        -- Risk: lower volatility = higher score
        percent_rank() over (
            partition by trade_date
            order by volatility_20d desc
        ) as rank_vol20_inverse,

        percent_rank() over (
            partition by trade_date
            order by volatility_60d desc
        ) as rank_vol60_inverse,

        percent_rank() over (
            partition by trade_date
            order by volatility_252d desc
        ) as rank_vol252_inverse,

        -- Drawdown: less negative = better
        percent_rank() over (
            partition by trade_date
            order by drawdown
        ) as rank_drawdown

    from base

),

scored as (

    select
        *,

        (
            0.15 * rank_return_20d
            + 0.15 * rank_return_60d
            + 0.10 * rank_return_252d
        ) as momentum_score,

        (
            0.08 * rank_ma20
            + 0.08 * rank_ma60
            + 0.09 * rank_ma252
        ) as trend_score,

        (
            0.07 * (1 - rank_vol20_inverse)
            + 0.07 * (1 - rank_vol60_inverse)
            + 0.06 * (1 - rank_vol252_inverse)
        ) as risk_score,

        (
            0.15 * rank_drawdown
        ) as drawdown_score

    from ranked

)

select
    trade_date,
    security_id,
    symbol,
    exchange,

    momentum_score,
    trend_score,
    risk_score,
    drawdown_score,

    momentum_score
        + trend_score
        + risk_score
        + drawdown_score
        as composite_score

from scored
