"""Warehouse connection. MotherDuck when a token is configured, otherwise the local DuckDB file."""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DB = ROOT / "warehouse" / "pulse.duckdb"
AS_OF = "2026-10-31"
AS_OF_LABEL = "Oct 31, 2026"


def secret(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource(show_spinner="Connecting to the warehouse...")
def get_connection() -> duckdb.DuckDBPyConnection:
    token = secret("MOTHERDUCK_TOKEN")
    if token:
        return duckdb.connect("md:pulse", config={"motherduck_token": token})
    if not LOCAL_DB.exists():
        st.error("No MOTHERDUCK_TOKEN configured and no local warehouse found. Run `python build_warehouse.py` first.")
        st.stop()
    return duckdb.connect(str(LOCAL_DB), read_only=True)


def source_label() -> str:
    return "MotherDuck · pulse.marts" if secret("MOTHERDUCK_TOKEN") else "Local DuckDB · pulse.marts"


@st.cache_data(ttl=900, show_spinner=False)
def run(sql: str) -> pd.DataFrame:
    return get_connection().cursor().execute(sql).df()
