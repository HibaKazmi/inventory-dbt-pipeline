with raw_rows as (
    select count(*) as n from {{ source('raw', 'raw_movements') }}
),

classified as (
    select count(*) as n, count(distinct raw_row_id) as distinct_n
    from {{ ref('int_movements_classified') }}
)

select r.n as raw_rows, c.n as classified_rows, c.distinct_n
from raw_rows as r
cross join classified as c
where r.n <> c.n or c.n <> c.distinct_n
