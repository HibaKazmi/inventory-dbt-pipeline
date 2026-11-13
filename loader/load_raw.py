from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import duckdb

DDL = """
create schema if not exists raw;

create table if not exists raw.load_log (
    load_id      integer primary key,
    source_file  varchar not null,
    file_sha256  varchar not null unique,
    row_count    integer not null,
    loaded_at    timestamp not null
);

create table if not exists raw.raw_movements (
    load_id            integer not null,
    source_file        varchar not null,
    source_row_number  integer not null,
    loaded_at          timestamp not null,
    movement_id        varchar,
    product_id         varchar,
    warehouse_id       varchar,
    movement_type      varchar,
    quantity           varchar,
    event_timestamp    varchar
);
"""


CSV_COLUMNS = (
    "{'movement_id': 'VARCHAR', 'product_id': 'VARCHAR', 'warehouse_id': 'VARCHAR', "
    "'movement_type': 'VARCHAR', 'quantity': 'VARCHAR', 'event_timestamp': 'VARCHAR'}"
)


def expand(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.glob("batch_*.csv")) if p.is_dir() else [p])
    return files


def load_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = con.execute("select load_id from raw.load_log where file_sha256 = ?", [sha]).fetchone()
    if existing:
        print(f"skip  {path.name}: identical content already loaded as load_id {existing[0]}")
        return

    con.execute("begin transaction")
    try:
        load_id = con.execute("select coalesce(max(load_id), 0) + 1 from raw.load_log").fetchone()[0]
        con.execute(
            f"""
            insert into raw.raw_movements
            select
                ? as load_id,
                ? as source_file,
                row_number() over () as source_row_number,
                current_timestamp::timestamp as loaded_at,
                movement_id, product_id, warehouse_id, movement_type, quantity, event_timestamp
            from read_csv(?, header = true, auto_detect = false, columns = {CSV_COLUMNS})
            """,
            [load_id, path.name, str(path)],
        )
        rows = con.execute("select count(*) from raw.raw_movements where load_id = ?", [load_id]).fetchone()[0]
        con.execute(
            "insert into raw.load_log values (?, ?, ?, ?, current_timestamp::timestamp)",
            [load_id, path.name, sha, rows],
        )
        con.execute("commit")
        print(f"load  {path.name}: {rows} rows as load_id {load_id}")
    except Exception:
        con.execute("rollback")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Load movement CSV files into DuckDB.")
    parser.add_argument("--db", type=Path, required=True, help="DuckDB database file")
    parser.add_argument("paths", type=Path, nargs="+", help="CSV files or folders containing batch_*.csv")
    args = parser.parse_args()

    con = duckdb.connect(str(args.db))
    try:
        con.execute(DDL)
        for path in expand(args.paths):
            load_file(con, path)
    finally:
        con.close()


if __name__ == "__main__":
    main()
