# Full refresh

Every `dbt build` rebuilds all models from `raw.raw_movements`.

```
pip install -r requirements.txt
python scripts/run_demo.py
```

- `generator/` - fixture and sample data
- `scripts/load_raw.py` - loads CSV files into DuckDB
- `dbt_project/` - models, tests, seeds
- `queries/` - the two reporting queries
- `results/` - output of the last run, including `pipeline_report.html`
- `rules.txt` - validation rules with examples

See the main README for setup, assumptions and tests.
