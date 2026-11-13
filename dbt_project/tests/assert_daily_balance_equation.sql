select *
from {{ ref('daily_inventory') }}
where closing_quantity <> opening_quantity + received_quantity - shipped_quantity + adjustment_quantity
   or negative_balance <> (closing_quantity < 0)
