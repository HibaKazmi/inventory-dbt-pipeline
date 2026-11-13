{% macro clean_text(column_name) -%}
    case
        when lower(trim({{ column_name }})) in ('', 'null') then null
        else trim({{ column_name }})
    end
{%- endmacro %}

{% macro to_business_date(timestamp_column) -%}
    cast({{ timestamp_column }} as date)
{%- endmacro %}
