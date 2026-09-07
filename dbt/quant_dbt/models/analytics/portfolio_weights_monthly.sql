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
            partition by date_trunc('month', trade_date)
        ) as month_end_date,

        max(trade_date) over () as latest_data_date

    from {{ ref('quant_rankings_v2') }}

),

monthly_signals as (

    select
        trade_date,
        security_id,
        symbol,
        exchange,
        rank,
        composite_score,
        selected_flag

    from rankings

    where trade_date = month_end_date

      -- Do not treat the current incomplete month
      -- as a completed month-end signal.
      and date_trunc('month', trade_date)
          < date_trunc('month', latest_data_date)

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
        when selected_flag = true then 0.5
        else 0.0
    end as target_weight

from monthly_signals
