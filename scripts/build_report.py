from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt_project"
TEMPLATE = Path(__file__).with_name("report_template.html")
SKIP_DIRS = {"target", "logs", "results", "__pycache__", "dbt_packages", "sample", ".venv", ".git"}
TEXT_SUFFIXES = {".py", ".sql", ".yml", ".yaml", ".csv", ".md", ".txt", ".json"}
MAX_FILE_BYTES = 60_000
DESCRIPTIONS = {
    "README.md": "Setup, commands, versions and design notes",
    "STORY.md": "The pipeline told as a plain-language story",
    "rules.txt": "Every validation rule, with example rows",
    "requirements.txt": "Pinned Python packages (dbt-core, dbt-duckdb)",
    ".gitignore": "Keeps the database file and large samples out of git",
    "generator": "Creates the input CSV files",
    "generator/generate_data.py": "Writes the fixture CSVs and the larger seeded sample",
    "loader": "Loads the CSV files into DuckDB",
    "loader/load_raw.py": "Loads CSV files into raw tables as text; skips files already loaded",
    "scripts": "Optional: runs every step at once and builds this report",
    "scripts/run_demo.py": "Runs the whole demo and collects the evidence",
    "scripts/build_report.py": "Builds this report",
    "scripts/report_template.html": "Page template for this report",
    "data": "Input files",
    "data/fixture": "Hand-made correctness fixture with known answers",
    "data/fixture/batch_001.csv": "First file: 15 hand-made rows",
    "data/fixture/batch_002_late.csv": "Late file: 3 rows",
    "data/fixture/expected": "Expected results of the two reporting queries",
    "queries": "The two reporting queries",
    "queries/daily_stock_by_warehouse.sql": "Reporting query 1: daily stock totals by warehouse",
    "queries/negative_stock_in_range.sql": "Reporting query 2: negative stock in a date range",
    "dbt_project": "The dbt project: models, tests, seeds, settings",
    "dbt_project/dbt_project.yml": "Project settings: folders, default materializations, vars",
    "dbt_project/profiles.yml": "Connection settings (a DuckDB file, no credentials)",
    "dbt_project/models": "One SELECT per file; dbt turns each into a view or table",
    "dbt_project/models/schema.yml": "Model descriptions and column tests",
    "dbt_project/models/staging": "Step 1: type and validate every row",
    "dbt_project/models/staging/_sources.yml": "Declares the raw tables the loader fills",
    "dbt_project/models/intermediate": "Step 2: a status for every row, daily totals",
    "dbt_project/models/marts": "Final outputs people query",
    "dbt_project/macros": "Reusable SQL snippets",
    "dbt_project/macros/clean_text.sql": "Tidy text fields; derive the business date",
    "dbt_project/seeds": "Expected answers, loaded as tables by dbt",
    "dbt_project/tests": "Rule tests: queries that must return 0 rows",
    "dbt_project/tests/fixture": "Exact-answer tests against the seeds",
    "dbt_project/tests/generic": "Reusable test types",
    "dbt_project/tests/generic/generic_tests.sql": "unique_combination_of_columns and expression_is_true",
}


def leading_comment(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            lines.append(s.lstrip("-").strip())
        elif s.startswith("{{") or not s:
            if lines:
                break
            continue
        else:
            break
    return " ".join(lines)


def describe_generic(meta: dict, column: str | None) -> str:
    name = meta.get("name", "")
    kw = meta.get("kwargs") or {}
    col = column or kw.get("column_name") or ""
    if name == "unique":
        return f"{col} has no repeated values"
    if name == "not_null":
        return f"{col} is never empty"
    if name == "accepted_values":
        return f"{col} is one of: {', '.join(map(str, kw.get('values', [])))}"
    if name == "relationships":
        return f"every {col} exists in {str(kw.get('to', '')).replace('ref(', '').strip(')')}.{kw.get('field', '')}"
    if name == "unique_combination_of_columns":
        return "one row per " + " + ".join(kw.get("combination_of_columns", []))
    if name == "expression_is_true":
        return "every row satisfies: " + " ".join(str(kw.get("expression", "")).split())
    return name


def project_path(original_file_path: str) -> str:
    return "dbt_project/" + original_file_path.replace("\\", "/")


def read_compiled(node: dict) -> str:
    path = DBT_DIR / "target" / "compiled" / node["package_name"] / node["original_file_path"]
    return path.read_text(encoding="utf-8") if path.exists() else ""


def dbt_info() -> dict:
    path = DBT_DIR / "target" / "manifest.json"
    if not path.exists():
        return {"nodes": {}}
    m = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, dict] = {}

    for uid, s in m.get("sources", {}).items():
        nodes[uid] = {"kind": "source", "name": f"{s['source_name']}.{s['name']}",
                      "relation": f"{s['schema']}.{s['identifier']}",
                      "materialized": "source", "description": s.get("description", ""),
                      "path": project_path(s["original_file_path"]), "depends_on": []}

    for uid, n in m.get("nodes", {}).items():
        rt = n["resource_type"]
        common = {"name": n["name"], "path": project_path(n["original_file_path"]),
                  "depends_on": n.get("depends_on", {}).get("nodes", [])}
        if rt == "model":
            nodes[uid] = {**common, "kind": "model", "materialized": n["config"]["materialized"],
                          "relation": f"{n['schema']}.{n.get('alias') or n['name']}",
                          "description": n.get("description", ""), "raw_code": n.get("raw_code", ""),
                          "compiled_code": n.get("compiled_code") or read_compiled(n),
                          "columns": {c: v.get("description", "") for c, v in n.get("columns", {}).items()}}
        elif rt == "seed":
            nodes[uid] = {**common, "kind": "seed", "materialized": "seed",
                          "relation": f"{n['schema']}.{n.get('alias') or n['name']}",
                          "description": n.get("description", "")}
        elif rt == "test":
            meta = n.get("test_metadata") or {}
            singular = not meta
            path_ = common["path"]
            group = ("fixture" if "/fixture/" in path_
                     else "rule" if singular
                     else "column" if n.get("column_name") else "rule")
            nodes[uid] = {**common, "kind": "test", "group": group,
                          "test_type": "singular" if singular else meta.get("name"),
                          "column": n.get("column_name"),
                          "attached": n.get("attached_node"),
                          "description": (leading_comment(n.get("raw_code", "")) if singular
                                          else describe_generic(meta, n.get("column_name"))),
                          "compiled_code": n.get("compiled_code") or read_compiled(n)}

    layers: dict[str, int] = {}

    def layer(uid: str) -> int:
        if uid in layers:
            return layers[uid]
        node = nodes.get(uid, {})
        deps = [d for d in node.get("depends_on", []) if nodes.get(d, {}).get("kind") in ("model", "source")]
        layers[uid] = 0 if node.get("kind") == "source" else 1 + max((layer(d) for d in deps), default=0)
        return layers[uid]

    for uid, node in nodes.items():
        if node["kind"] in ("model", "source"):
            node["layer"] = layer(uid)
    for uid, node in nodes.items():
        if node["kind"] == "test":
            target = node.get("attached")
            if not target:
                cands = [d for d in node["depends_on"] if nodes.get(d, {}).get("kind") in ("model", "source")]
                target = max(cands, key=lambda d: nodes[d]["layer"]) if cands else None
            node["target"] = target
            if target and nodes.get(target, {}).get("kind") == "source" and node["group"] != "fixture":
                node["group"] = "source"
    return {"nodes": nodes}


def repo_tree() -> list[dict]:
    entries: list[dict] = []

    def walk(folder: Path, depth: int) -> None:
        items = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for p in items:
            rel = p.relative_to(ROOT).as_posix()
            if p.is_dir():
                if p.name in SKIP_DIRS:
                    continue
                entries.append({"path": rel, "name": p.name, "kind": "dir", "depth": depth,
                                "description": DESCRIPTIONS.get(rel, "")})
                walk(p, depth + 1)
            else:
                if p.suffix in (".duckdb", ".wal") or p.name.endswith(".duckdb.wal"):
                    continue
                entry = {"path": rel, "name": p.name, "kind": "file", "depth": depth,
                         "description": DESCRIPTIONS.get(rel, ""), "size": p.stat().st_size}
                if (p.suffix in TEXT_SUFFIXES or p.name == ".gitignore") and p.stat().st_size <= MAX_FILE_BYTES:
                    entry["content"] = p.read_text(encoding="utf-8", errors="replace")
                entries.append(entry)

    walk(ROOT, 0)
    return entries


def build(data_path: Path, out_path: Path) -> Path:
    report = json.loads(data_path.read_text(encoding="utf-8"))
    payload = {"report": report, "dbt": dbt_info(), "repo": repo_tree()}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__REPORT_DATA__", blob, 1)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HTML pipeline report.")
    parser.add_argument("--data", type=Path, default=ROOT / "results" / "report_data.json")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "pipeline_report.html")
    args = parser.parse_args()
    print(build(args.data, args.out))


if __name__ == "__main__":
    main()
