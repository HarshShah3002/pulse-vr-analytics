# Pulse: Engagement Intelligence for At-Home VR Therapy

An end-to-end analytics project for a (fictional) company that rents VR therapy headsets to members with chronic pain and anxiety, billed to insurance as monthly equipment rental and supported by remote peer coaches.

The goal: give business leaders (founders, product, operations, care team, partnerships) one trusted place to answer **who starts, who stays, why they leave, and what it costs**, and let them ask those questions in plain English through Omni's AI.

## What leaders can answer
- **Activation:** How many members start using their headset, and how fast? What changed when we introduced a 48-hour welcome call?
- **Retention:** Weekly cohort retention heatmap. Does first-week usage predict who stays?
- **Engagement status:** Who is active, at risk, lapsed? Can we trust the CRM status for members without wifi?
- **Sessions:** How long, how often, which modules work?
- **Devices:** Which firmware batches fail, and what does downtime do to retention?
- **Billing:** How many billed months had zero use? Which plans deny claims?
- **Outcomes:** How much does self-reported pain drop for members who complete the program?

## Architecture
```
Python simulator  ->  raw CSVs  ->  DuckDB / MotherDuck
                                     raw -> staging (cleaning) -> marts (business tables)
                                                                    |
                                                         Omni semantic model
                                         (metric definitions, synonyms, AI context, sample queries)
                                                                    |
                                               Omni dashboards + Omni Agent (plain-English Q&A)
```

## Repo layout
| Path | What it is |
|---|---|
| `generator/generate_data.py` | Day-by-day member journey simulator |
| `sql/staging`, `sql/marts` | Cleaning and business models |
| `build_warehouse.py` | Builds locally or into MotherDuck |
| `validation/` | Benchmark checks and headline business queries |
| `omni/` | Semantic model: views, relationships, topics, model-level AI context |
| `docs/` | Data dictionary, simulation assumptions, setup guide |

## About the data
All data is simulated, calibrated to published benchmarks for home VR and digital pain programs, with realistic business events and data quality problems injected on purpose. See `docs/assumptions.md`. The SQL, metric definitions and Omni model run unchanged on a real export with the same tables.

## Quick start
See `docs/setup_motherduck_omni.md`.
