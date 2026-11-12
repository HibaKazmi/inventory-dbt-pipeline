{{
    config(
        materialized = 'incremental',
        unique_key = 'raw_row_id',
        incremental_strategy = 'delete+insert',
        on_schema_change = 'fail'
    )
}}

select
    raw_row_id,
    load_id,
    source_file,
    source_row_number,
    movement_id,
    product_id,
    warehouse_id,
    movement_type,
    quantity_text           as quantity,
    event_timestamp_text    as event_timestamp,
    rejection_reason
from {{ ref('int_movements_classified') }}
where row_status = 'rejected'
{% if is_incremental() %}
  and load_id > (select coalesce(max(load_id), 0) from {{ this }})
{% endif %}
