{{ config(materialized='table') }}

with configurations as (

    select
        configuration_id,
        strategy_id,
        upper(coalesce(signal_frequency, 'WEEKLY')) as signal_frequency

    from {{ source('analytics', 'strategy_config_version') }}

    where status in ('VALIDATED', 'FROZEN')

),

weights as (

    select distinct
        trade_date as as_of_date,
        configuration_id,
        strategy_id

    from {{ ref('portfolio_weights_v2') }}

),

latest_data as (

    select
        configuration_id,
        strategy_id,
        max(as_of_date) as latest_data_date

    from weights

    group by
        configuration_id,
        strategy_id

),

trading_dates as (

    select
        trade_date

    from {{ ref('stg_trading_calendar') }}

    where is_trading_day = true

),

period_calendar as (

    select
        c.configuration_id,
        c.strategy_id,
        c.signal_frequency,
        td.trade_date,

        {{ signal_period_expr(
            'td.trade_date',
            'c.signal_frequency'
        ) }} as signal_period

    from configurations c

    cross join trading_dates td

),

period_ends as (

    select
        configuration_id,
        strategy_id,
        signal_frequency,
        signal_period,
        max(trade_date) as signal_date

    from period_calendar

    group by
        configuration_id,
        strategy_id,
        signal_frequency,
        signal_period

),

completed_periods as (

    select
        p.configuration_id,
        p.strategy_id,
        p.signal_frequency,
        p.signal_period,
        p.signal_date

    from period_ends p

    inner join latest_data ld
        on p.configuration_id = ld.configuration_id
       and p.strategy_id = ld.strategy_id

    inner join weights w
        on p.configuration_id = w.configuration_id
       and p.strategy_id = w.strategy_id
       and p.signal_date = w.as_of_date

    where p.signal_date <= ld.latest_data_date

),

with_execution_dates as (

    select
        p.*,

        (
            select min(td.trade_date)

            from trading_dates td

            where td.trade_date > p.signal_date

        ) as execution_date

    from completed_periods p

),

signal_windows as (

    select
        configuration_id,
        strategy_id,
        signal_frequency,
        signal_period,
        signal_date,
        execution_date,

        lag(signal_date) over (
            partition by configuration_id, strategy_id
            order by signal_date
        ) as previous_signal_date,

        lead(signal_date) over (
            partition by configuration_id, strategy_id
            order by signal_date
        ) as next_signal_date,

        lead(execution_date) over (
            partition by configuration_id, strategy_id
            order by signal_date
        ) as next_execution_date

    from with_execution_dates

)

select *

from signal_windows

where execution_date is not null
