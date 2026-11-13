select
    warehouse_id,
    inventory_date,
    count(*)                                   as product_count,
    sum(opening_quantity)::bigint              as opening_quantity,
    sum(received_quantity)::bigint             as received_quantity,
    sum(shipped_quantity)::bigint              as shipped_quantity,
    sum(adjustment_quantity)::bigint           as adjustment_quantity,
    sum(closing_quantity)::bigint              as closing_quantity,
    count(*) filter (where negative_balance)   as negative_product_count
from main.daily_inventory
where inventory_date between $start_date and $end_date
group by warehouse_id, inventory_date
order by warehouse_id, inventory_date
