{{ config(materialized='view') }}

with accepted as (

    select * from {{ ref('int_movements_classified') }}
    where row_status = 'accepted'

)

select
    product_id,
    warehouse_id,
    business_date                                                              as activity_date,
    sum(case when movement_type = 'receipt'    then quantity else 0 end)::bigint as received_quantity,
    sum(case when movement_type = 'shipment'   then quantity else 0 end)::bigint as shipped_quantity,
    sum(case when movement_type = 'adjustment' then quantity else 0 end)::bigint as adjustment_quantity,
    sum(case when movement_type = 'shipment'   then -quantity else quantity end)::bigint as net_change
from accepted
group by product_id, warehouse_id, business_date
