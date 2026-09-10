with orders as (

    select *
    from {{ ref('trade_orders_v2') }}

),

prices as (

    select
        trade_date,
        security_id,
        close as execution_price
    from {{ ref('fact_daily_prices') }}

)

select
    o.signal_date,
    o.execution_date,
    o.security_id,
    o.symbol,
    o.exchange,
    o.configuration_id,
    o.strategy_id,
    o.side,
    o.previous_weight,
    o.current_weight,
    o.order_weight,
    p.execution_price,
    o.order_status,

    case
        when p.execution_price is not null
            then 'FILLED'

        when o.execution_date > current_date
            then 'PENDING'

        else 'DATA_MISSING'
    end as execution_status

from orders o

left join prices p
    on p.trade_date = o.execution_date
   and p.security_id = o.security_id
