import streamlit as st

from lib import charts as c
from lib import metrics
from lib.db import source_label

c.page_header("How it's built", "Architecture, metric definitions, and what's simulated.")

st.graphviz_chart("""
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#f3f2ee", color="#c3c2b7", fontname="Helvetica", fontsize=11, margin="0.18,0.1"];
  edge [color="#898781", arrowsize=0.7];
  sim  [label="Python simulator\\nmembers, orders, sessions,\\noutreach, invoices"];
  raw  [label="raw\\n(as exported)"];
  stg  [label="staging\\n(cleaned, deduplicated)"];
  mart [label="marts\\n(business tables)"];
  ml   [label="Models\\nlapse risk, outreach effect"];
  app  [label="Streamlit app\\nmetrics layer + 11 pages", fillcolor="#cde2fb"];
  ai   [label="AI layer (OpenRouter)\\nbriefings, Ask Pulse,\\nfact check", fillcolor="#cde2fb"];
  subgraph cluster_md { label="MotherDuck (cloud DuckDB)"; fontname="Helvetica"; fontsize=11; color="#c3c2b7"; style="rounded"; raw; stg; mart; }
  sim -> raw -> stg -> mart -> ml -> mart;
  mart -> app; app -> ai;
}
""")

st.markdown(f"""
**Current source:** {source_label()}

| Layer | What it does |
|---|---|
| Simulator | Plays out each member's journey day by day: referral, delivery, welcome call, first session, habit or drop-off, device faults, returns, monthly billing. Includes real-world mess: duplicate CRM records, late-syncing sessions, missing phones. |
| Warehouse | MotherDuck (cloud DuckDB). `raw` holds the exports as they arrive, `staging` cleans and deduplicates them, and `marts` holds the business tables: members, sessions, cohort weeks, orders, billing, outreach and CRM accuracy. |
| Models | Logistic regression for 30-day lapse risk (with reasons coaches can say out loud); outreach and week-one effects estimated three ways. Results are written back to the warehouse. |
| Metrics layer | Every number in this app comes from one named query in `app/lib/metrics.py`, so definitions never drift between pages. |
| App | Streamlit pages for leadership, operations and the care team, reading live from the warehouse. |
| AI layer | Briefings for five audiences, written only from a computed fact sheet and fact-checked; Ask Pulse turns plain-English questions into guarded, read-only SQL. |
""")

st.subheader("Metric definitions")
st.dataframe([{"Metric": k, "Definition": v} for k, v in metrics.DEFINITIONS.items()], hide_index=True, width="stretch")

st.subheader("About the data")
st.markdown("""
All data is **simulated** for a fictional company, Lumora Health, because real member-level health data is protected.
It is calibrated to published benchmarks for at-home VR and digital pain programs (short sessions of about 6 to 10 minutes,
an 8-week core program, most drop-off in the first weeks, capped monthly rental under HCPCS E1905).
Every query, model and definition here would run unchanged on a real export with the same tables.

Code: [github.com/HarshShah3002/pulse-vr-analytics](https://github.com/HarshShah3002/pulse-vr-analytics) · Built by Harsh Shah
""")
