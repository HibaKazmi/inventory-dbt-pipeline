from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

COLUMNS = ["movement_id", "product_id", "warehouse_id", "movement_type", "quantity", "event_timestamp"]
WAREHOUSES = ["W01", "W02"]
FIXTURE_BATCH_1 = [
    ("M001", "P101", "W01", "receipt", "20", "2026-03-01 09:00:00"),
    ("M002", "P101", "W01", "shipment", "5", "2026-03-01 14:00:00"),
    ("M002", "P101", "W01", "shipment", "5", "2026-03-01 14:00:00"),
    ("M003", "P101", "W01", "adjustment", "-2", "2026-03-02 10:00:00"),
    ("M004", "P101", "W01", "shipment", "30", "2026-03-03 11:00:00"),
    ("M005", "", "W01", "receipt", "8", "2026-03-03 12:00:00"),
    ("M006", "P102", "W02", "receipt", "10", "2026-03-01 08:00:00"),
    ("M007", "P102", "W02", "shipment", "4", "2026-03-03 16:00:00"),
    ("M008", "P101", "W02", "receipt", "7", "2026-03-02 09:30:00"),
    ("M009", "P102", "W02", "transfer", "3", "2026-03-02 11:00:00"),
    ("M010", "P101", "W01", "shipment", "0", "2026-03-02 12:00:00"),
    ("M011", "P102", "W01", "adjustment", "0", "2026-03-02 13:00:00"),
    ("M012", "P101", "W02", "receipt", "2.5", "2026-03-03 09:00:00"),
    ("M013", "P102", "W02", "receipt", "5", "not-a-timestamp"),
    ("M014", "P102", "W02", "receipt", "6", "2026-03-04T10:00:00"),
]

FIXTURE_BATCH_2_LATE = [
    ("M015", "P101", "W01", "receipt", "10", "2026-03-02 15:00:00"),
    ("M016", "P102", "W02", "shipment", "12", "2026-03-02 18:00:00"),
    ("M002", "P101", "W01", "shipment", "5", "2026-03-01 14:00:00"),
]

FIXTURE_BATCH_3_EXTEND = [
    ("M017", "P101", "W02", "shipment", "3", "2026-03-05 09:00:00"),
    ("M018", "P103", "W01", "receipt", "4", "2026-03-05 10:00:00"),
]


def write_csv(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def generate_fixture(out: Path) -> None:
    write_csv(out / "batch_001.csv", FIXTURE_BATCH_1)
    write_csv(out / "batch_002_late.csv", FIXTURE_BATCH_2_LATE)
    write_csv(out / "batch_003_extend.csv", FIXTURE_BATCH_3_EXTEND)
    print(f"fixture written to {out}: batch_001.csv ({len(FIXTURE_BATCH_1)} rows), "
          f"batch_002_late.csv ({len(FIXTURE_BATCH_2_LATE)} rows), "
          f"batch_003_extend.csv ({len(FIXTURE_BATCH_3_EXTEND)} rows)")


INVALID_KINDS = [
    "missing_movement_id",
    "missing_product_id",
    "missing_warehouse_id",
    "missing_event_timestamp",
    "invalid_movement_type",
    "non_integer_quantity",
    "unparseable_event_timestamp",
    "non_positive_quantity",
    "zero_adjustment_quantity",
]


def _valid_row(rng: random.Random, movement_id: str, products: list[str], ts: datetime) -> list[str]:
    movement_type = rng.choices(["receipt", "shipment", "adjustment"], weights=[45, 45, 10])[0]
    if movement_type == "adjustment":
        qty = rng.choice([-1, 1]) * rng.randint(1, 5)
    else:
        qty = rng.randint(1, 50)
    return [movement_id, rng.choice(products), rng.choice(WAREHOUSES), movement_type, str(qty),
            ts.strftime("%Y-%m-%d %H:%M:%S")]


def _make_invalid(rng: random.Random, row: list[str], kind: str) -> list[str]:
    row = list(row)
    if kind == "missing_movement_id":
        row[0] = ""
    elif kind == "missing_product_id":
        row[1] = ""
    elif kind == "missing_warehouse_id":
        row[2] = ""
    elif kind == "missing_event_timestamp":
        row[5] = ""
    elif kind == "invalid_movement_type":
        row[3] = rng.choice(["transfer", "return", "unknown"])
    elif kind == "non_integer_quantity":
        row[4] = rng.choice(["2.5", "abc", "1e3"])
    elif kind == "unparseable_event_timestamp":
        row[5] = rng.choice(["not-a-timestamp", "2026-02-30 10:00:00", "31/03/2026"])
    elif kind == "non_positive_quantity":
        row[3] = rng.choice(["receipt", "shipment"])
        row[4] = rng.choice(["0", "-3"])
    elif kind == "zero_adjustment_quantity":
        row[3] = "adjustment"
        row[4] = "0"
    return row


def generate_sample(out: Path, rows: int, products: int, days: int, batches: int, seed: int,
                    duplicate_rate: float, invalid_rate: float, late_rows: int, start: str) -> None:
    rng = random.Random(seed)
    product_ids = [f"P{1000 + i}" for i in range(products)]
    start_dt = datetime.fromisoformat(start)
    span_seconds = days * 86400 - 1

    timestamps = sorted(start_dt + timedelta(seconds=rng.randint(0, span_seconds)) for _ in range(rows))
    base: list[list[str]] = []
    expected = {"valid_unique": 0, "invalid": 0, "duplicate": 0}
    for i, ts in enumerate(timestamps, start=1):
        row = _valid_row(rng, f"S{i:08d}", product_ids, ts)
        if rng.random() < invalid_rate:
            row = _make_invalid(rng, row, rng.choice(INVALID_KINDS))
            expected["invalid"] += 1
        else:
            expected["valid_unique"] += 1
        base.append(row)

    batch_size = -(-len(base) // batches)
    max_processed_date = None
    for b in range(batches):
        chunk = base[b * batch_size:(b + 1) * batch_size]
        out_rows: list[list[str]] = []
        for row in chunk:
            out_rows.append(row)
            if rng.random() < duplicate_rate:
                out_rows.append(list(row))
                if _is_invalid(row):
                    expected["invalid"] += 1
                else:
                    expected["duplicate"] += 1
        write_csv(out / f"batch_{b + 1:03d}.csv", [tuple(r) for r in out_rows])
        max_processed_date = chunk[-1][5][:10] if chunk else max_processed_date

    late: list[list[str]] = []
    late_window_end = start_dt + timedelta(days=days - 1)
    for i in range(1, late_rows + 1):
        ts = start_dt + timedelta(seconds=rng.randint(0, int((late_window_end - start_dt).total_seconds())))
        late.append(_valid_row(rng, f"L{i:08d}", product_ids, ts))
        expected["valid_unique"] += 1
    redelivered = [r for r in rng.sample(base, k=min(5, len(base))) if not _is_invalid(r)]
    late.extend(list(r) for r in redelivered)
    expected["duplicate"] += len(redelivered)
    write_csv(out / f"batch_{batches + 1:03d}_late.csv", [tuple(r) for r in late])

    raw_rows = sum(1 for p in out.glob("batch_*.csv") for _ in p.open(encoding="utf-8")) - len(list(out.glob("batch_*.csv")))
    manifest = {
        "seed": seed, "rows": rows, "products": products, "days": days, "batches": batches,
        "duplicate_rate": duplicate_rate, "invalid_rate": invalid_rate, "late_rows": late_rows,
        "expected_raw_rows": raw_rows,
        "expected_accepted": expected["valid_unique"],
        "expected_rejected": expected["invalid"],
        "expected_duplicate": expected["duplicate"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


def _is_invalid(row: list[str]) -> bool:
    movement_id, product, warehouse, mtype, qty, ts = row
    if not all([movement_id, product, warehouse, mtype, qty, ts]):
        return True
    if mtype not in ("receipt", "shipment", "adjustment"):
        return True
    try:
        q = int(qty)
    except ValueError:
        return True
    try:
        datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    if mtype in ("receipt", "shipment") and q <= 0:
        return True
    return mtype == "adjustment" and q == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate inventory movement CSV files.")
    sub = parser.add_subparsers(dest="mode", required=True)

    f = sub.add_parser("fixture", help="write the small correctness fixture")
    f.add_argument("--out", type=Path, default=Path("data/fixture"))

    s = sub.add_parser("sample", help="write a larger reproducible sample")
    s.add_argument("--out", type=Path, default=Path("data/sample"))
    s.add_argument("--rows", type=int, default=50_000)
    s.add_argument("--products", type=int, default=200)
    s.add_argument("--days", type=int, default=90)
    s.add_argument("--batches", type=int, default=3)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--duplicate-rate", type=float, default=0.02)
    s.add_argument("--invalid-rate", type=float, default=0.03)
    s.add_argument("--late-rows", type=int, default=500)
    s.add_argument("--start", default="2026-01-01")

    args = parser.parse_args()
    if args.mode == "fixture":
        generate_fixture(args.out)
    else:
        for old in args.out.glob("batch_*.csv"):
            old.unlink()
        generate_sample(args.out, args.rows, args.products, args.days, args.batches, args.seed,
                        args.duplicate_rate, args.invalid_rate, args.late_rows, args.start)


if __name__ == "__main__":
    main()
