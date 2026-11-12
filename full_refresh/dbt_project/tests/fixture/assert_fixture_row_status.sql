{{ config(enabled = var('fixture_stage') is not none) }}

with expected as (
    select raw_row_id, movement_id, row_status, rejection_reason, duplicate_of_raw_row_id
    from {{ ref('expected_row_status') }}
    where stage = '{{ var("fixture_stage") }}'
),

actual as (
    select raw_row_id, movement_id, row_status, rejection_reason, duplicate_of_raw_row_id
    from {{ ref('int_movements_classified') }}
    where row_status <> 'accepted'
)

select 'missing_from_actual' as issue, * from (select * from expected except select * from actual)
union all
select 'unexpected_in_actual' as issue, * from (select * from actual except select * from expected)
