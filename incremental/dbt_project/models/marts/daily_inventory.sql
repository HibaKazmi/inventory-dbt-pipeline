{{
    config(
        materialized = 'incremental',
        unique_key = ['product_id', 'warehouse_id', 'inventory_date'],
        incremental_strategy = 'delete+insert',
        on_schema_change = 'fail'
    )
}}

with movements as (

    select * from {{ ref('clean_movements') }}

),

dataset_end as (

    select max(business_date) as last_date, max(load_id) as last_load_id
    from movements

),

{% if is_incremental() %}

previous_run as (

    select
        coalesce(max(processed_load_id), 0) as processed_load_id,
        max(inventory_date)                 as previous_last_date
    from {{ this }}

),

recompute_points as (

    select m.product_id, m.warehouse_id, min(m.business_date) as recompute_from
    from movements as m
    cross join previous_run as p
    where m.load_id > p.processed_load_id
    group by m.product_id, m.warehouse_id

    union all

    select t.product_id, t.warehouse_id, cast(p.previous_last_date + interval 1 day as date)
    from (select distinct product_id, warehouse_id from {{ this }}) as t
    cross join previous_run as p
    cross join dataset_end as e
    where e.last_date > p.previous_last_date

),

recompute_window as (

    select
        r.product_id,
        r.warehouse_id,
        r.recompute_from,
        coalesce(t.closing_quantity, 0) as starting_balance
    from (
        select product_id, warehouse_id, min(recompute_from) as recompute_from
        from recompute_points
        group by product_id, warehouse_id
    ) as r
    left join {{ this }} as t
        on  t.product_id     = r.product_id
        and t.warehouse_id   = r.warehouse_id
        and t.inventory_date = cast(r.recompute_from - interval 1 day as date)

),

{% else %}

recompute_window as (

    select product_id, warehouse_id, min(business_date) as recompute_from, 0::bigint as starting_balance
    from movements
    group by product_id, warehouse_id

),

{% endif %}

activity as (

    select
        m.product_id,
        m.warehouse_id,
        m.business_date                                                              as activity_date,
        sum(case when m.movement_type = 'receipt'    then m.quantity else 0 end)::bigint as received_quantity,
        sum(case when m.movement_type = 'shipment'   then m.quantity else 0 end)::bigint as shipped_quantity,
        sum(case when m.movement_type = 'adjustment' then m.quantity else 0 end)::bigint as adjustment_quantity,
        sum(m.signed_quantity)::bigint                                               as net_change
    from movements as m
    join recompute_window as w
        on  w.product_id   = m.product_id
        and w.warehouse_id = m.warehouse_id
        and m.business_date >= w.recompute_from
    group by m.product_id, m.warehouse_id, m.business_date

),

date_spine as (

    select
        w.product_id,
        w.warehouse_id,
        w.starting_balance,
        cast(unnest(generate_series(w.recompute_from, e.last_date, interval 1 day)) as date) as inventory_date
    from recompute_window as w
    cross join dataset_end as e

),

daily as (

    select
        s.product_id,
        s.warehouse_id,
        s.inventory_date,
        s.starting_balance,
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
        (starting_balance + sum(net_change) over (
            partition by product_id, warehouse_id
            order by inventory_date
            rows between unbounded preceding and current row
        ))::bigint as closing_quantity
    from daily

)

select
    b.product_id,
    b.warehouse_id,
    b.inventory_date,
    b.closing_quantity - b.net_change  as opening_quantity,
    b.received_quantity,
    b.shipped_quantity,
    b.adjustment_quantity,
    b.closing_quantity,
    b.closing_quantity < 0             as negative_balance,
    e.last_load_id                     as processed_load_id
from balances as b
cross join dataset_end as e
