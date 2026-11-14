# Inventory movement pipeline

Batch pipeline that turns warehouse movement files into validated movements and
daily inventory balances, built with dbt Core on DuckDB.

Loom walkthrough: https://www.loom.com/share/d53172f7f05f42878fb9c5fa92397b26, https://www.loom.com/share/53f1e88ef71045b1afc04fd0c831b0bb, https://www.loom.com/share/77460c8c6b9d452a804b2e6c72063348 (3 videos of 5 mins each, making it 15mins altogether.)

## Versions

| | |
|---|---|
| Python | 3.13.7 |
| dbt-core | 1.12.7 |
| dbt-duckdb | 1.11.1 |
| DuckDB | 2.0.0 |

## Layout

The pipeline runs in this order:

```
generator/      1. writes the input CSV files
data/fixture/   2. the input files (hand-made rows with known results)
loader/         3. loads the CSV files into DuckDB, as text
dbt_project/    4. all transformations and tests
  models/staging/        type the fields, check the rules
  models/intermediate/   accepted / rejected / duplicate, daily totals
  models/marts/          clean_movements, rejected_movements, daily_inventory
queries/        5. the two reporting queries
scripts/        optional: runs steps 1-5 in one go and builds an HTML report
```

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No credentials needed. `dbt_project/profiles.yml` points to `dbt_project/warehouse.duckdb`.

## Run step by step

From the repo root:

```
python generator/generate_data.py fixture --out data/fixture
python loader/load_raw.py --db dbt_project/warehouse.duckdb data/fixture/batch_001.csv
cd dbt_project
dbt debug
dbt build --vars "{fixture_stage: initial}"
```

Late batch (still inside `dbt_project/`):

```
python ../loader/load_raw.py --db warehouse.duckdb ../data/fixture/batch_002_late.csv
dbt build --vars "{fixture_stage: after_late}"
```

`--vars` turns on the tests that compare the output with the expected results
for that stage. Leave it out for any other data.

The reporting queries are in `queries/`. Run them against
`dbt_project/warehouse.duckdb`, replacing `$start_date` and `$end_date` with dates.

All steps at once: `python scripts/run_demo.py` (writes `results/`, including `pipeline_report.html`).

## Models

```
raw.raw_movements          loaded by loader/load_raw.py, all columns as text
stg_movements              view    types the fields, adds rejection_reason
int_movements_classified   table   accepted / rejected / duplicate per row
clean_movements            table   accepted movements with signed_quantity
rejected_movements         table   rejected rows with reason
movement_reconciliation    view    row counts per file
int_daily_activity         view    daily totals per product and warehouse
daily_inventory            table   one row per product, warehouse and day
```

## Assumptions

- Timestamps have no time zone and are treated as UTC. Business date is the UTC date.
- Each rejected row gets one reason: the first rule it fails, in the order listed in `rules.txt`.
- Duplicates are checked only among valid rows. The first copy by load order is kept.
- Only exact duplicates are expected. A repeated movement_id with different values fails a test.
- `movement_type` is trimmed and lower-cased before checking.
- Daily rows run from each product/warehouse's first valid movement to the last movement date in the data.

## Fixture

| After | raw | accepted | rejected | duplicate | daily rows |
|---|---|---|---|---|---|
| batch_001 | 15 | 8 | 6 | 1 | 11 |
| batch_002_late | 18 | 10 | 6 | 2 | 11 |

P101 at W01 closes at 15, 13, -17, -17 after the first file, and 15, 23, -7, -7
after the late file. Expected rows are in `dbt_project/seeds/` and
`data/fixture/expected/`.

## Reruns and late data

The loader skips files it has already loaded (sha256 in `raw.load_log`).
dbt keeps one row per movement_id, and every table is rebuilt from raw, so a
rerun gives the same result. Balances are a running sum by date, so a late
movement changes its own date and every later date.

## Tests

- Not null, unique and accepted values on the main columns.
- Balance: closing = opening + received - shipped + adjustment, opening = previous closing.
- No missing days per product/warehouse.
- Each accepted movement counted once in stock.
- Every raw row ends up accepted, rejected or duplicate.
- Fixture results compared with the expected seeds.

## Data volume

Fixture: 18 rows. Sample: _fill in_.

```
python generator/generate_data.py sample --out data/sample --rows 50000
python loader/load_raw.py --db dbt_project/warehouse.duckdb data/sample
cd dbt_project
dbt build
```

## Limitation

`daily_inventory` is recalculated over the full history on every run, so it gets
slower as data grows. The next step would be incremental models: give each
loaded file a load_id, process only new load_ids, and rebuild balances only from
the earliest changed date for the affected product and warehouse.
