{{
    config(
        materialized = 'incremental',
        unique_key = 'movement_id',
        incremental_strategy = 'delete+insert',
        on_schema_change = 'fail'
    )
}}

select
    movement_id,
    product_id,
    warehouse_id,
    movement_type,
    business_date,
    event_timestamp,
    quantity,
    case movement_type
        when 'receipt'    then quantity
        when 'shipment'   then -quantity
        when 'adjustment' then quantity
    end                                       as signed_quantity,
    raw_row_id,
    source_file,
    load_id
from {{ ref('int_movements_classified') }}
where row_status = 'accepted'
{% if is_incremental() %}
  and load_id > (select coalesce(max(load_id), 0) from {{ this }})
{% endif %}
