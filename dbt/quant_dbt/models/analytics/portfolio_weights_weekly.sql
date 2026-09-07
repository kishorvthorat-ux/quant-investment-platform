with rankings as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag,

        max(trade_date) over (
            partition by date_trunc('week', trade_date)
        ) as week_end_date

    from {{ ref('quant_rankings_v2') }}

),

weekly_signals as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag

    from rankings

    where trade_date = week_end_date

)

select
    trade_date,
    security_id,
    symbol,
    exchange,
    rank,
    composite_score,
    selected_flag,
    case
    	when selected_flag = true
        then 1.0 / {{ var('top_n', 2) }}
    else 0.0
	end as target_weight

from weekly_signals
