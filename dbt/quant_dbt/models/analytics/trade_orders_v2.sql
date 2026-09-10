select
    signal_date,
    execution_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    previous_signal_date,
    previous_rank,
    current_rank,
    previous_weight,
    current_weight,
    current_composite_score,

    signal as side,

    case
        when signal = 'BUY'
            then current_weight
        when signal = 'SELL'
            then previous_weight
    end as order_weight,

    'PENDING' as order_status

from {{ ref('weekly_signals_v2') }}

where signal in ('BUY', 'SELL')
