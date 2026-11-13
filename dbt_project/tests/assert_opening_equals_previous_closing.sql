with ordered as (
    select
        *,
        lag(closing_quantity) over (
            partition by product_id, warehouse_id order by inventory_date
        ) as previous_closing
    from {{ ref('daily_inventory') }}
)

select *
from ordered
where opening_quantity <> coalesce(previous_closing, 0)
