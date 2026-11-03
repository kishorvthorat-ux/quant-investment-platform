{% macro signal_period_expr(date_column, frequency_column) %}
case
    when upper(coalesce({{ frequency_column }}, 'WEEKLY')) = 'MONTHLY'
        then date_trunc('month', {{ date_column }})
    when upper(coalesce({{ frequency_column }}, 'WEEKLY')) in (
        'LONG_TERM',
        'LONG-TERM',
        'QUARTERLY',
        'QUARTER'
    )
        then date_trunc('quarter', {{ date_column }})
    else date_trunc('week', {{ date_column }})
end
{% endmacro %}
