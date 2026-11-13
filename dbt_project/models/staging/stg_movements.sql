with source as (

    select * from {{ source('raw', 'raw_movements') }}

),

normalised as (

    select
        concat(load_id, '-', source_row_number)          as raw_row_id,
        load_id,
        source_file,
        source_row_number,
        {{ clean_text('movement_id') }}                  as movement_id,
        {{ clean_text('product_id') }}                   as product_id,
        {{ clean_text('warehouse_id') }}                 as warehouse_id,
        lower({{ clean_text('movement_type') }})         as movement_type,
        {{ clean_text('quantity') }}                     as quantity_text,
        {{ clean_text('event_timestamp') }}              as event_timestamp_text
    from source

),

typed as (

    select
        *,
        case
            when regexp_full_match(quantity_text, '[+-]?[0-9]+')
                then try_cast(quantity_text as bigint)
        end                                              as quantity,
        try_strptime(
            event_timestamp_text,
            ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']
        )                                                as event_timestamp
    from normalised

),

validated as (

    select
        *,
        case
            when movement_id is null                         then 'missing_movement_id'
            when product_id is null                          then 'missing_product_id'
            when warehouse_id is null                        then 'missing_warehouse_id'
            when movement_type is null                       then 'missing_movement_type'
            when quantity_text is null                       then 'missing_quantity'
            when event_timestamp_text is null                then 'missing_event_timestamp'
            when movement_type not in ('receipt', 'shipment', 'adjustment')
                                                             then 'invalid_movement_type'
            when quantity is null                            then 'non_integer_quantity'
            when event_timestamp is null                     then 'unparseable_event_timestamp'
            when movement_type in ('receipt', 'shipment') and quantity <= 0
                                                             then 'non_positive_quantity'
            when movement_type = 'adjustment' and quantity = 0
                                                             then 'zero_adjustment_quantity'
        end                                              as rejection_reason
    from typed

)

select
    raw_row_id,
    load_id,
    source_file,
    source_row_number,
    movement_id,
    product_id,
    warehouse_id,
    movement_type,
    quantity_text,
    quantity,
    event_timestamp_text,
    event_timestamp,
    {{ to_business_date('event_timestamp') }}           as business_date,
    rejection_reason
from validated
