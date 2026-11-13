{{ config(enabled = var('fixture_stage') is not none) }}

with actual as (
    select
        count(*)                                         as raw_rows,
        count(*) filter (where row_status = 'accepted')  as accepted_rows,
        count(*) filter (where row_status = 'rejected')  as rejected_rows,
        count(*) filter (where row_status = 'duplicate') as duplicate_rows
    from {{ ref('int_movements_classified') }}
),

expected as (
    select raw_rows, accepted_rows, rejected_rows, duplicate_rows
    from {{ ref('expected_movement_counts') }}
    where stage = '{{ var("fixture_stage") }}'
)

select 'missing_from_actual' as issue, * from (select * from expected except select * from actual)
union all
select 'unexpected_in_actual' as issue, * from (select * from actual except select * from expected)
