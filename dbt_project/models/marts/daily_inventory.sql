with activity as (

    select * from {{ ref('int_daily_activity') }}

),

dataset_end as (

    select max(activity_date) as last_date from activity

),

combinations as (

    select product_id, warehouse_id, min(activity_date) as first_date
    from activity
    group by product_id, warehouse_id

),

date_spine as (

    select
        c.product_id,
        c.warehouse_id,
        cast(unnest(generate_series(c.first_date, e.last_date, interval 1 day)) as date) as inventory_date
    from combinations as c
    cross join dataset_end as e

),

daily as (

    select
        s.product_id,
        s.warehouse_id,
        s.inventory_date,
        coalesce(a.received_quantity, 0)   as received_quantity,
        coalesce(a.shipped_quantity, 0)    as shipped_quantity,
        coalesce(a.adjustment_quantity, 0) as adjustment_quantity,
        coalesce(a.net_change, 0)          as net_change
    from date_spine as s
    left join activity as a
        on  a.product_id    = s.product_id
        and a.warehouse_id  = s.warehouse_id
        and a.activity_date = s.inventory_date

),

balances as (

    select
        *,
        sum(net_change) over (
            partition by product_id, warehouse_id
            order by inventory_date
            rows between unbounded preceding and current row
        )::bigint as closing_quantity
    from daily

)

select
    product_id,
    warehouse_id,
    inventory_date,
    closing_quantity - net_change  as opening_quantity,
    received_quantity,
    shipped_quantity,
    adjustment_quantity,
    closing_quantity,
    closing_quantity < 0           as negative_balance
from balances
