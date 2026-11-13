with expected as (
    select
        product_id,
        warehouse_id,
        min(business_date) as first_date,
        (select max(business_date) from {{ ref('clean_movements') }}) as last_date
    from {{ ref('clean_movements') }}
    group by product_id, warehouse_id
),

actual as (
    select
        product_id,
        warehouse_id,
        min(inventory_date) as first_date,
        max(inventory_date) as last_date,
        count(*)            as day_count
    from {{ ref('daily_inventory') }}
    group by product_id, warehouse_id
)

select e.*, a.first_date as actual_first, a.last_date as actual_last, a.day_count
from expected as e
full outer join actual as a
    on a.product_id = e.product_id and a.warehouse_id = e.warehouse_id
where a.product_id is null
   or e.product_id is null
   or a.first_date <> e.first_date
   or a.last_date  <> e.last_date
   or a.day_count  <> date_diff('day', e.first_date, e.last_date) + 1
