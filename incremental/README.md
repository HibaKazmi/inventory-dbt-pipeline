# Incremental

Same pipeline as `full_refresh/`, but `int_movements_classified`,
`clean_movements`, `rejected_movements` and `daily_inventory` are incremental.

```
pip install -r requirements.txt
python scripts/run_demo.py
```

- Each loaded file gets a `load_id`. A run only processes load_ids higher than
  the ones already in the table.
- A movement_id already accepted in an earlier run is marked duplicate.
- `daily_inventory` is rebuilt per product/warehouse from the earliest date that
  changed, starting from the stored closing balance of the day before. Rows are
  replaced with `delete+insert` on product, warehouse and date.
- `dbt build --full-refresh` must give the same result. This is checked by
  `assert_incremental_matches_full_recompute` and by `run_demo.py`.

Limitations: raw rows must not be edited in place, and a change to the
validation rules needs a `--full-refresh`.
