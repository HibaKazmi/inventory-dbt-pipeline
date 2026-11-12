{{ config(enabled = var('fixture_stage') is not none) }}

with expected as (
    select product_id, warehouse_id, inventory_date, opening_quantity, received_quantity,
           shipped_quantity, adjustment_quantity, closing_quantity, negative_balance
    from {{ ref('expected_daily_inventory') }}
    where stage = '{{ var("fixture_stage") }}'
),

actual as (
    select product_id, warehouse_id, inventory_date, opening_quantity, received_quantity,
           shipped_quantity, adjustment_quantity, closing_quantity, negative_balance
    from {{ ref('daily_inventory') }}
)

select 'missing_from_actual' as issue, * from (select * from expected except select * from actual)
union all
select 'unexpected_in_actual' as issue, * from (select * from actual except select * from expected)
