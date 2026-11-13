# Inventory movement pipeline

Batch pipeline that turns warehouse movement files into validated movements and
daily inventory balances, built with dbt Core on DuckDB.

Loom walkthrough: _add link here_

Every `dbt build` rebuilds all models from the raw data.

## Versions

| | |
|---|---|
| Python | 3.13.7 |
| dbt-core | 1.12.7 |
| dbt-duckdb | 1.11.1 |
| DuckDB | 2.0.0 |

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No credentials needed. `dbt_project/profiles.yml` points to a local DuckDB file.

## Run

```
python scripts/run_demo.py
```

This generates the fixture, loads it, runs `dbt build`, reruns the same input,
loads the late batch and a later-dated batch, runs the two reporting queries and
checks everything against the expected results. Output goes to `results/`.

Step by step:

```
python generator/generate_data.py fixture --out data/fixture
python scripts/load_raw.py --db warehouse.duckdb data/fixture/batch_001.csv
dbt build --project-dir dbt_project --profiles-dir dbt_project --vars "{fixture_stage: initial}"
python scripts/load_raw.py --db warehouse.duckdb data/fixture/batch_002_late.csv
dbt build --project-dir dbt_project --profiles-dir dbt_project --vars "{fixture_stage: after_late}"
```

Larger sample: `python scripts/run_demo.py --dataset sample --rows 50000`

## Models

```
raw.raw_movements          loaded by scripts/load_raw.py, all columns as text
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

`data/fixture/` has three files with known results:

| After | raw | accepted | rejected | duplicate | daily rows |
|---|---|---|---|---|---|
| batch_001 | 15 | 8 | 6 | 1 | 11 |
| batch_002_late | 18 | 10 | 6 | 2 | 11 |
| batch_003_extend | 20 | 12 | 6 | 2 | 15 |

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

Fixture: 20 rows. Sample: _fill in from `results/sample_summary.json`_.

## Limitation

`daily_inventory` is recalculated over the full history on every run, so it gets
slower as data grows. The next step would be incremental models: give each
loaded file a load_id, process only new load_ids, and rebuild balances only from
the earliest changed date for the affected product and warehouse.

`results/pipeline_report.html` shows the lineage, SQL and output of each model
for the last run.
