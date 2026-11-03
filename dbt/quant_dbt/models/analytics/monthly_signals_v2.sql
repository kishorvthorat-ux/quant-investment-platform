{{ config(materialized='view') }}

select
    signal_date,
    execution_date,
    security_id,
    symbol,
    exchange,
    configuration_id,
    strategy_id,
    signal_frequency,
    previous_signal_date,
    previous_rank,
    current_rank,
    previous_weight,
    current_weight,
    current_composite_score,
    signal
from {{ ref('strategy_signals_v2') }}
where signal_frequency = 'MONTHLY'
