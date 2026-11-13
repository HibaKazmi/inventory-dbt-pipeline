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
