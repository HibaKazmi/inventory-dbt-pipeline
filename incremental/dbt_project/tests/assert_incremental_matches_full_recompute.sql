with movements as (
    select * from {{ ref('clean_movements') }}
),

activity as (
    select
        product_id, warehouse_id, business_date as activity_date,
        sum(case when movement_type = 'receipt'    then quantity else 0 end) as received_quantity,
        sum(case when movement_type = 'shipment'   then quantity else 0 end) as shipped_quantity,
        sum(case when movement_type = 'adjustment' then quantity else 0 end) as adjustment_quantity,
        sum(signed_quantity) as net_change
    from movements
    group by 1, 2, 3
),

spine as (
    select c.product_id, c.warehouse_id,
           cast(unnest(generate_series(c.first_date, e.last_date, interval 1 day)) as date) as inventory_date
    from (select product_id, warehouse_id, min(activity_date) as first_date from activity group by 1, 2) as c
    cross join (select max(activity_date) as last_date from activity) as e
),

recomputed as (
    select
        s.product_id, s.warehouse_id, s.inventory_date,
        coalesce(a.received_quantity, 0)   as received_quantity,
        coalesce(a.shipped_quantity, 0)    as shipped_quantity,
        coalesce(a.adjustment_quantity, 0) as adjustment_quantity,
        sum(coalesce(a.net_change, 0)) over (
            partition by s.product_id, s.warehouse_id order by s.inventory_date
        ) as closing_quantity
    from spine as s
    left join activity as a
        on a.product_id = s.product_id and a.warehouse_id = s.warehouse_id
       and a.activity_date = s.inventory_date
),

expected as (
    select product_id, warehouse_id, inventory_date,
           (received_quantity)::bigint, (shipped_quantity)::bigint, (adjustment_quantity)::bigint,
           (closing_quantity)::bigint
    from recomputed
),

actual as (
    select product_id, warehouse_id, inventory_date, received_quantity, shipped_quantity,
           adjustment_quantity, closing_quantity
    from {{ ref('daily_inventory') }}
)

select 'missing_from_incremental' as issue, * from (select * from expected except select * from actual)
union all
select 'unexpected_in_incremental' as issue, * from (select * from actual except select * from expected)
