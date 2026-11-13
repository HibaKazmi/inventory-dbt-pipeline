{{ config(materialized='view') }}

select
    load_id,
    source_file,
    count(*)                                             as raw_rows,
    count(*) filter (where row_status = 'accepted')      as accepted_rows,
    count(*) filter (where row_status = 'rejected')      as rejected_rows,
    count(*) filter (where row_status = 'duplicate')     as duplicate_rows
from {{ ref('int_movements_classified') }}
group by load_id, source_file
