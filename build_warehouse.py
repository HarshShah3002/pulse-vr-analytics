"""
Build the Pulse warehouse.

  python build_warehouse.py                 -> local DuckDB file: warehouse/pulse.duckdb
  python build_warehouse.py --motherduck    -> MotherDuck database "pulse" (needs MOTHERDUCK_TOKEN env var)

Layers: raw (CSV as-is) -> staging (cleaned) -> marts (business tables the app reads).
"""
import argparse
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
TABLES = ["members", "orders", "headsets", "sessions", "outreach_touches", "invoices", "coaches"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motherduck", action="store_true")
    a = ap.parse_args()

    if a.motherduck:
        if not os.environ.get("MOTHERDUCK_TOKEN"):
            raise SystemExit("Set MOTHERDUCK_TOKEN first (MotherDuck > Settings > Access tokens).")
        con = duckdb.connect("md:")
        con.execute("create database if not exists pulse")
        con.execute("use pulse")
    else:
        (ROOT / "warehouse").mkdir(exist_ok=True)
        con = duckdb.connect(str(ROOT / "warehouse" / "pulse.duckdb"))

    con.execute("create schema if not exists raw")
    for t in TABLES:
        con.execute(f"create or replace table raw.{t} as select * from read_csv_auto('{RAW / (t + '.csv')}', header=true)")
        print(f"raw.{t:18s} {con.execute(f'select count(*) from raw.{t}').fetchone()[0]:>9,d}")

    for f in sorted((ROOT / "sql").rglob("*.sql"), key=lambda p: p.name):  # 01_, 02_ order
        con.execute(f.read_text())
        print(f"ran {f.relative_to(ROOT)}")

    for (schema, name) in con.execute(
        "select table_schema, table_name from information_schema.tables "
        "where table_schema = 'marts' order by 2").fetchall():
        n = con.execute(f"select count(*) from {schema}.{name}").fetchone()[0]
        print(f"{schema}.{name:22s} {n:>9,d}")
    con.close()


if __name__ == "__main__":
    main()
