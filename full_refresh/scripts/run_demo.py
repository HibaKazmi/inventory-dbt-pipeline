from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import duckdb

FLAVOUR = "full_refresh"
ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt_project"
QUERIES = ROOT / "queries"
RESULTS = ROOT / "results"
DB = ROOT / "warehouse.duckdb"
ENV = {**os.environ, "DUCKDB_PATH": str(DB), "PYTHONIOENCODING": "utf-8"}

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_report

checks: list[tuple[str, bool, str]] = []

REPORT: dict = {"flavour": FLAVOUR, "stages": [], "log": [], "reports": {}, "late_changes": None}
current_step = {"title": ""}
last_dbt_results: list[dict] = []


SNAPSHOT_TABLES = [
    ("raw.load_log", "load_id"),
    ("raw.raw_movements", "load_id, source_row_number"),
    ("main.stg_movements", "load_id, source_row_number"),
    ("main.int_movements_classified", "load_id, source_row_number"),
    ("main.clean_movements", "load_id, raw_row_id"),
    ("main.rejected_movements", "load_id, source_row_number"),
    ("main.movement_reconciliation", "load_id"),
    ("main.int_daily_activity", "product_id, warehouse_id, activity_date"),
    ("main.daily_inventory", "product_id, warehouse_id, inventory_date"),
]

SNAPSHOT_ROW_LIMIT = 300


def banner(text: str) -> None:
    current_step["title"] = text
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def short(cmd: list[str]) -> str:
    text = " ".join('"' + c.replace('"', "") + '"' if c.startswith("{") else c for c in cmd)
    for long, plain in [(sys.executable, "python"), (dbt_exe(), "dbt"), (str(ROOT) + os.sep, ""), (str(ROOT), ".")]:
        text = text.replace(long, plain)
    return text.replace("\\", "/")


def run(cmd: list[str]) -> str:
    print("$ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, env=ENV, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out, end="" if out.endswith("\n") else "\n", flush=True)
    is_dbt = Path(cmd[0]).stem == "dbt"
    kept = [ln for ln in out.splitlines()
            if not is_dbt or any(k in ln for k in ("Done.", "Finished running", "ERROR", "FAIL", "WARN", "Completed"))]
    REPORT["log"].append({"step": current_step["title"], "command": short(cmd),
                          "output": "\n".join(kept).strip(), "ok": proc.returncode == 0})
    if proc.returncode != 0:
        raise SystemExit(f"command failed with exit code {proc.returncode}: {short(cmd)}")
    return out


def dbt_exe() -> str:
    local = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    return str(local) if local.exists() else (shutil.which("dbt") or "dbt")


def dbt(*args: str, stage: str | None = None) -> float:
    cmd = [dbt_exe(), *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if stage:
        cmd += ["--vars", json.dumps({"fixture_stage": stage})]
    start = time.perf_counter()
    run(cmd)
    elapsed = time.perf_counter() - start
    read_run_results()
    return elapsed


def read_run_results() -> None:
    global last_dbt_results
    path = DBT_DIR / "target" / "run_results.json"
    if not path.exists():
        last_dbt_results = []
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    last_dbt_results = [
        {"unique_id": r["unique_id"], "status": str(r.get("status")),
         "time": round(r.get("execution_time") or 0, 3), "failures": r.get("failures"),
         "message": r.get("message")}
        for r in data.get("results", [])
    ]


def load(*paths: Path) -> None:
    run([sys.executable, str(ROOT / "scripts" / "load_raw.py"), "--db", str(DB), *map(str, paths)])


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (date, datetime)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    return str(v)


def query(sql: str, params: dict | None = None) -> tuple[list[str], list[tuple[str, ...]]]:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        cur = con.execute(sql, params or {})
        cols = [d[0] for d in cur.description]
        return cols, [tuple(fmt(v) for v in row) for row in cur.fetchall()]
    finally:
        con.close()


def write_csv(path: Path, cols: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


def read_expected(path: Path, stage: str) -> tuple[list[str], list[tuple[str, ...]]]:
    with path.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["stage"] == stage]
    cols = [c for c in rows[0].keys() if c != "stage"] if rows else []
    return cols, [tuple(r[c] for c in cols) for r in rows]


def snapshot() -> dict:
    _, counts = query("""
        select count(*),
               count(*) filter (where row_status = 'accepted'),
               count(*) filter (where row_status = 'rejected'),
               count(*) filter (where row_status = 'duplicate')
        from main.int_movements_classified""")
    cols, daily = query("""
        select product_id, warehouse_id, inventory_date, opening_quantity, received_quantity,
               shipped_quantity, adjustment_quantity, closing_quantity, negative_balance
        from main.daily_inventory
        order by product_id, warehouse_id, inventory_date""")
    _, clean = query("select count(*) from main.clean_movements")
    return {
        "counts": dict(zip(["raw", "accepted", "rejected", "duplicate"], map(int, counts[0]))),
        "clean_rows": int(clean[0][0]),
        "daily_cols": cols,
        "daily": daily,
    }


def describe(s: dict) -> str:
    c = s["counts"]
    return (f"raw={c['raw']} accepted={c['accepted']} rejected={c['rejected']} "
            f"duplicate={c['duplicate']} daily_rows={len(s['daily'])}")


def capture_stage(key: str, title: str, note: str, snap: dict) -> None:
    tables = {}
    for name, order in SNAPSHOT_TABLES:
        try:
            cols, rows = query(f"select * from {name} order by {order} limit {SNAPSHOT_ROW_LIMIT}")
        except duckdb.CatalogException:
            continue
        _, total = query(f"select count(*) from {name}")
        tables[name] = {"columns": cols, "rows": [list(r) for r in rows], "total": int(total[0][0])}
    REPORT["stages"].append({"key": key, "title": title, "note": note, "counts": snap["counts"],
                             "daily_rows": len(snap["daily"]), "tables": tables,
                             "dbt_results": list(last_dbt_results)})


def run_reports(stage: str, start: str, end: str, expected_dir: Path | None) -> None:
    for name in ["daily_stock_by_warehouse", "negative_stock_in_range"]:
        sql = (QUERIES / f"{name}.sql").read_text()
        cols, rows = query(sql, {"start_date": start, "end_date": end})
        write_csv(RESULTS / f"report_{name}_{stage}.csv", cols, rows)
        print(f"\n{name} ({start} .. {end}), stage={stage}")
        print("  " + " | ".join(cols))
        for r in rows:
            print("  " + " | ".join(r))
        entry = {"sql": sql, "params": {"start_date": start, "end_date": end},
                 "columns": cols, "rows": [list(r) for r in rows], "matches_expected": None}
        if expected_dir:
            exp_cols, exp_rows = read_expected(expected_dir / f"report_{name}.csv", stage)
            ok = exp_cols == cols and exp_rows == rows
            entry["matches_expected"] = ok
            check(f"report {name} matches expected [{stage}]", ok, f"{len(rows)} rows")
        REPORT["reports"].setdefault(stage, {})[name] = entry


def fixture_flow() -> None:
    data = ROOT / "data" / "fixture"
    expected_dir = data / "expected"

    banner("1. Fresh database, generate fixture, load batch_001, dbt build")
    run([sys.executable, str(ROOT / "generator" / "generate_data.py"), "fixture", "--out", str(data)])
    load(data / "batch_001.csv")
    dbt("build", stage="initial")
    s1 = snapshot()
    write_csv(RESULTS / "daily_inventory_initial.csv", s1["daily_cols"], s1["daily"])
    check("initial counts", s1["counts"] == {"raw": 15, "accepted": 8, "rejected": 6, "duplicate": 1},
          describe(s1))
    check("P101/W01 closing 15, 13, -17 on 03-01..03-03 (PDF example)",
          [r[-2] for r in s1["daily"] if r[0] == "P101" and r[1] == "W01"][:3] == ["15", "13", "-17"])
    capture_stage("initial", "1. Initial load",
                  "batch_001.csv loaded (15 rows) and dbt build run.", s1)

    banner("2. Rerun identical inputs (loader + dbt build)")
    load(data / "batch_001.csv")
    dbt("build", stage="initial")
    s2 = snapshot()
    check("rerun keeps row counts and balances identical", s1 == s2, describe(s2))
    capture_stage("rerun", "2. Rerun same file",
                  "batch_001.csv offered again: the loader skipped it, dbt rebuilt everything.", s2)

    banner("3. Load the late-arriving batch, dbt build")
    load(data / "batch_002_late.csv")
    dbt("build", stage="after_late")
    s3 = snapshot()
    write_csv(RESULTS / "daily_inventory_after_late.csv", s3["daily_cols"], s3["daily"])
    check("after-late counts", s3["counts"] == {"raw": 18, "accepted": 10, "rejected": 6, "duplicate": 2},
          describe(s3))
    before = {r[:3]: r for r in s1["daily"]}
    changed = [(*r, before.get(r[:3], ("",) * len(r))[-2]) for r in s3["daily"] if before.get(r[:3]) != r]
    write_csv(RESULTS / "late_batch_changed_rows.csv", s3["daily_cols"] + ["closing_before_late"], changed)
    REPORT["late_changes"] = {"columns": s3["daily_cols"] + ["closing_before_late"],
                              "rows": [list(r) for r in changed]}
    print("\nrows changed by the late batch (closing_before_late in last column):")
    for r in changed:
        print("  " + " | ".join(r))
    expected_changed = {(p, w, d) for p, w in [("P101", "W01"), ("P102", "W02")]
                        for d in ["2026-03-02", "2026-03-03", "2026-03-04"]}
    check("late batch changes its business date and every later day, nothing earlier",
          {r[:3] for r in changed} == expected_changed, f"{len(changed)} rows changed")
    capture_stage("after_late", "3. Late batch",
                  "batch_002_late.csv loaded (3 rows: two late movements dated 03-02, one re-sent M002).", s3)

    banner("4. Rerun again after the late batch")
    load(data / "batch_001.csv", data / "batch_002_late.csv")
    dbt("build", stage="after_late")
    s4 = snapshot()
    check("second rerun keeps everything identical", s3 == s4, describe(s4))

    banner("Reporting queries after the late batch")
    run_reports("after_late", "2026-03-01", "2026-03-04", expected_dir)

    banner("5. Load a batch with a LATER date (2026-03-05), dbt build")
    load(data / "batch_003_extend.csv")
    dbt("build", stage="after_extend")
    s5 = snapshot()
    write_csv(RESULTS / "daily_inventory_after_extend.csv", s5["daily_cols"], s5["daily"])
    check("after-extend counts", s5["counts"] == {"raw": 20, "accepted": 12, "rejected": 6, "duplicate": 2},
          describe(s5))
    before = set(s4["daily"])
    added = [r for r in s5["daily"] if r not in before]
    expected_added = {("P101", "W01", "2026-03-05"), ("P101", "W02", "2026-03-05"),
                      ("P102", "W02", "2026-03-05"), ("P103", "W01", "2026-03-05")}
    check("later date adds one carried-forward day per product/warehouse, earlier rows unchanged",
          before <= set(s5["daily"]) and {r[:3] for r in added} == expected_added,
          f"{len(added)} rows added, {len(before)} earlier rows unchanged")
    capture_stage("after_extend", "4. Later date",
                  "batch_003_extend.csv loaded (2 rows dated 03-05, after everything loaded so far).", s5)
    run_reports("after_extend", "2026-03-01", "2026-03-05", expected_dir)

    if FLAVOUR == "incremental":
        banner("6. dbt build --full-refresh must equal the incremental result")
        dbt("build", "--full-refresh", stage="after_extend")
        s6 = snapshot()
        check("full refresh equals incremental result", s5 == s6, describe(s6))


def fixture_initial_reports() -> None:
    banner("Reporting queries on the initial stage (fresh rebuild of batch_001 only)")
    reset_db()
    data = ROOT / "data" / "fixture"
    load(data / "batch_001.csv")
    dbt("build", stage="initial")
    run_reports("initial", "2026-03-01", "2026-03-04", data / "expected")


def sample_flow(args) -> None:
    data = ROOT / "data" / "sample"
    banner(f"Sample dataset: {args.rows} base rows")
    run([sys.executable, str(ROOT / "generator" / "generate_data.py"), "sample", "--out", str(data),
         "--rows", str(args.rows), "--seed", str(args.seed)])
    manifest = json.loads((data / "manifest.json").read_text())
    base_files = sorted(p for p in data.glob("batch_*.csv") if "late" not in p.name)
    late_files = sorted(data.glob("batch_*_late.csv"))

    banner("Sample: load base batches, dbt build")
    load(*base_files)
    t1 = dbt("build")
    s1 = snapshot()
    print(describe(s1))
    capture_stage("initial", "1. Base batches", f"{len(base_files)} base files loaded.", s1)

    banner("Sample: rerun")
    t2 = dbt("build")
    s2 = snapshot()
    check("sample rerun identical", s1 == s2, f"dbt build {t2:.1f}s")
    capture_stage("rerun", "2. Rerun", "dbt build run again on the same raw rows.", s2)

    banner("Sample: late batch")
    load(*late_files)
    t3 = dbt("build")
    s3 = snapshot()
    expected = {"raw": manifest["expected_raw_rows"], "accepted": manifest["expected_accepted"],
                "rejected": manifest["expected_rejected"], "duplicate": manifest["expected_duplicate"]}
    check("sample counts match generator manifest", s3["counts"] == expected,
          f"actual {s3['counts']} expected {expected}")
    capture_stage("after_late", "3. Late batch", "Late file loaded.", s3)
    if FLAVOUR == "incremental":
        t4 = dbt("build", "--full-refresh")
        s4 = snapshot()
        check("sample full refresh equals incremental result", s3 == s4, f"full refresh {t4:.1f}s")

    summary = {"flavour": FLAVOUR, "raw_rows": s3["counts"]["raw"], "clean_movements": s3["clean_rows"],
               "daily_inventory_rows": len(s3["daily"]), "first_build_s": round(t1, 1),
               "rerun_build_s": round(t2, 1), "late_batch_build_s": round(t3, 1)}
    (RESULTS / "sample_summary.json").write_text(json.dumps(summary, indent=2))
    REPORT["sample_summary"] = summary
    print(json.dumps(summary, indent=2))


def reset_db() -> None:
    for p in [DB, DB.with_suffix(".duckdb.wal")]:
        if p.exists():
            p.unlink()


def write_report(dataset: str) -> None:
    lines = [f"# Demo results ({FLAVOUR})", "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {'PASS' if ok else 'FAIL'} | {d} |" for n, ok, d in checks]
    (RESULTS / "demo_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    REPORT["dataset"] = dataset
    REPORT["generated_at"] = datetime.now().isoformat(timespec="seconds")
    REPORT["checks"] = [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]
    suffix = "" if dataset == "fixture" else "_sample"
    data_path = RESULTS / f"report_data{suffix}.json"
    data_path.write_text(json.dumps(REPORT, indent=1), encoding="utf-8")
    html_path = build_report.build(data_path, RESULTS / f"pipeline_report{suffix}.html")
    print(f"\nInteractive report: {html_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline demo end to end.")
    parser.add_argument("--dataset", choices=["fixture", "sample"], default="fixture")
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)
    reset_db()
    if args.dataset == "fixture":
        fixture_flow()
        fixture_initial_reports()
    else:
        sample_flow(args)
    write_report(args.dataset)

    failed = [n for n, ok, _ in checks if not ok]
    banner(f"{len(checks) - len(failed)}/{len(checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
