with validated as (

    select * from {{ ref('stg_movements') }}

),

valid_occurrences as (

    select
        raw_row_id,
        row_number() over w   as occurrence,
        first_value(raw_row_id) over w as first_raw_row_id
    from validated
    where rejection_reason is null
    window w as (partition by movement_id order by load_id, source_row_number)

)

select
    v.*,
    case
        when v.rejection_reason is not null then 'rejected'
        when o.occurrence = 1               then 'accepted'
        else                                     'duplicate'
    end                                                     as row_status,
    case when o.occurrence > 1 then o.first_raw_row_id end  as duplicate_of_raw_row_id
from validated as v
left join valid_occurrences as o
    on v.raw_row_id = o.raw_row_id
