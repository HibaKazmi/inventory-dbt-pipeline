{{
    config(
        materialized = 'incremental',
        unique_key = 'raw_row_id',
        incremental_strategy = 'delete+insert',
        on_schema_change = 'fail'
    )
}}

with new_rows as (

    select * from {{ ref('stg_movements') }}
    {% if is_incremental() %}
    where load_id > (select coalesce(max(load_id), 0) from {{ this }})
    {% endif %}

),

previously_accepted as (

    {% if is_incremental() %}
    select movement_id, raw_row_id as first_raw_row_id
    from {{ this }}
    where row_status = 'accepted'
    {% else %}
    select null::varchar as movement_id, null::varchar as first_raw_row_id
    where false
    {% endif %}

),

valid_occurrences as (

    select
        raw_row_id,
        movement_id,
        row_number() over w            as occurrence_in_run,
        first_value(raw_row_id) over w as first_raw_row_id_in_run
    from new_rows
    where rejection_reason is null
    window w as (partition by movement_id order by load_id, source_row_number)

)

select
    n.*,
    case
        when n.rejection_reason is not null then 'rejected'
        when p.movement_id is not null      then 'duplicate'
        when o.occurrence_in_run = 1        then 'accepted'
        else                                     'duplicate'
    end as row_status,
    case
        when n.rejection_reason is not null then null
        when p.movement_id is not null      then p.first_raw_row_id
        when o.occurrence_in_run > 1        then o.first_raw_row_id_in_run
    end as duplicate_of_raw_row_id
from new_rows as n
left join valid_occurrences as o
    on n.raw_row_id = o.raw_row_id
left join previously_accepted as p
    on n.movement_id = p.movement_id
   and n.rejection_reason is null
