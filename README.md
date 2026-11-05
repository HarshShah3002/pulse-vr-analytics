# Pulse: Engagement Intelligence for At-Home VR Therapy

An end-to-end analytics project for a (fictional) company that rents VR therapy headsets to members with chronic pain and anxiety, billed to insurance as monthly equipment rental and supported by remote peer coaches.

The goal: give business leaders (founders, product, operations, care team, partnerships) one trusted place to answer **who starts, who stays, why they leave, what it costs, and what to do next**, explained in plain language with AI.

## What leaders can answer
- **Activation:** How many members start using their headset, and how fast? What changed with the 48-hour welcome call?
- **Retention:** Weekly cohort retention heatmap. Does first-week usage predict who stays?
- **Engagement status:** Who is active, at risk, lapsed? Can we trust the CRM status for members without wifi?
- **Sessions:** How long, how often, which modules work?
- **Devices:** Which firmware batches fail, and what does downtime do to retention?
- **Billing:** How many billed months had zero use? Which plans deny claims?
- **Care team:** Who should coaches call this week, and why?
- **Next steps:** Six recommendations sized with the data, including care bundles with therapy and movement partners.

## Architecture
```
Python simulator -> raw CSVs -> MotherDuck (cloud DuckDB)
                                  raw -> staging (cleaning) -> marts (business tables)
                                                                 |        ^
                                                                 |   analytics/run_models.py
                                                                 |   (lapse risk model, outreach and week-one effects)
                                                                 v
                                          Streamlit app (app/): metrics layer, 11 pages
                                                                 |
                                          AI layer via OpenRouter: audience briefings,
                                          Ask Pulse (text to guarded SQL), number fact check
```

## The app
Eleven pages: executive overview, activation, retention (cohort heatmap), engagement and CRM status accuracy, coach outreach impact, devices and billing, a care team call list driven by an explainable risk model, recommendations, AI briefings for five audiences (every number fact-checked against the warehouse), Ask Pulse (plain-English questions turned into read-only SQL), and how it's built.

## Repo layout
| Path | What it is |
|---|---|
| `generator/generate_data.py` | Day-by-day member journey simulator |
| `sql/staging`, `sql/marts` | Cleaning and business models |
| `build_warehouse.py` | Builds locally or into MotherDuck |
| `analytics/run_models.py` | Lapse risk model and outreach / week-one effect estimates, written back to the warehouse |
| `app/` | Streamlit app: `lib/` (connection, metrics layer, charts, AI) and `views/` (pages) |
| `validation/` | Benchmark checks and headline business queries |
| `docs/` | Setup and run guide, data dictionary, simulation assumptions |

## About the data
All data is simulated, calibrated to published benchmarks for home VR and digital pain programs, with realistic business events and data quality problems injected on purpose. See `docs/assumptions.md`. The SQL, metric definitions and models run unchanged on a real export with the same tables.

## Quick start
See `docs/run_app.md`.
