with scores as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        momentum_score,
        trend_score,
        risk_score,
        drawdown_score,
        composite_score

    from {{ ref('quant_scores') }}

),

ranked as (

    select
        *,
        row_number() over (
            partition by trade_date
            order by composite_score desc, symbol
        ) as rank

    from scores

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
    composite_score,
    rank,

    case
        when rank <= 2 then true
        else false
    end as selected_flag

from ranked
