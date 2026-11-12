with classified as (
    select * from {{ ref('int_movements_classified') }}
)

select d.raw_row_id, d.movement_id, d.duplicate_of_raw_row_id
from classified as d
join classified as a
    on a.raw_row_id = d.duplicate_of_raw_row_id
where d.row_status = 'duplicate'
  and (
         d.product_id      is distinct from a.product_id
      or d.warehouse_id    is distinct from a.warehouse_id
      or d.movement_type   is distinct from a.movement_type
      or d.quantity        is distinct from a.quantity
      or d.event_timestamp is distinct from a.event_timestamp
  )
