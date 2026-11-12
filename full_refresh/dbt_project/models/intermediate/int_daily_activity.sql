{{ config(materialized='view') }}

select
    product_id,
    warehouse_id,
    business_date                                                              as activity_date,
    sum(case when movement_type = 'receipt'    then quantity else 0 end)::bigint as received_quantity,
    sum(case when movement_type = 'shipment'   then quantity else 0 end)::bigint as shipped_quantity,
    sum(case when movement_type = 'adjustment' then quantity else 0 end)::bigint as adjustment_quantity,
    sum(signed_quantity)::bigint                                               as net_change
from {{ ref('clean_movements') }}
group by product_id, warehouse_id, business_date
