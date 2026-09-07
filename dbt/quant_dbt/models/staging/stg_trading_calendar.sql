select
    trade_date,
    exchange,
    is_trading_day,
    holiday_name
from {{ source('raw', 'trading_calendar') }}
