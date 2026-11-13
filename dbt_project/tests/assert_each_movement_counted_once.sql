with movement_totals as (
    select
        product_id,
        warehouse_id,
        sum(case when movement_type = 'receipt'    then quantity else 0 end) as received,
        sum(case when movement_type = 'shipment'   then quantity else 0 end) as shipped,
        sum(case when movement_type = 'adjustment' then quantity else 0 end) as adjusted,
        sum(signed_quantity)                                                 as net
    from {{ ref('clean_movements') }}
    group by product_id, warehouse_id
),

inventory_totals as (
    select
        product_id,
        warehouse_id,
        sum(received_quantity)   as received,
        sum(shipped_quantity)    as shipped,
        sum(adjustment_quantity) as adjusted,
        arg_max(closing_quantity, inventory_date) as final_closing
    from {{ ref('daily_inventory') }}
    group by product_id, warehouse_id
)

select m.*, i.received as inv_received, i.shipped as inv_shipped,
       i.adjusted as inv_adjusted, i.final_closing
from movement_totals as m
full outer join inventory_totals as i
    on i.product_id = m.product_id and i.warehouse_id = m.warehouse_id
where i.product_id is null
   or m.product_id is null
   or m.received <> i.received
   or m.shipped  <> i.shipped
   or m.adjusted <> i.adjusted
   or m.net      <> i.final_closing
