select
    product_id,
    warehouse_id,
    count(*)                    as negative_days,
    min(inventory_date)         as first_negative_date,
    max(inventory_date)         as last_negative_date,
    min(closing_quantity)       as lowest_closing_quantity
from main.daily_inventory
where negative_balance
  and inventory_date between $start_date and $end_date
group by product_id, warehouse_id
order by product_id, warehouse_id
