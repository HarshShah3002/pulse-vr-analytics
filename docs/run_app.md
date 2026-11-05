# Setup and running the app

## 1. Install (once)
```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Build the warehouse
```bash
python generator/generate_data.py    # optional: the CSVs are already in data/raw
python build_warehouse.py            # local file: warehouse/pulse.duckdb (raw -> staging -> marts)
python analytics/run_models.py       # lapse risk model and effect estimates, written to marts
```

To use MotherDuck (cloud DuckDB) instead:
1. Create a free account at motherduck.com and a **Read/Write** access token.
2. Put it in `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example`) or export it as `MOTHERDUCK_TOKEN`.
3. Run the same two build commands with `--motherduck`:
```bash
python build_warehouse.py --motherduck
python analytics/run_models.py --motherduck
```

## 3. Run locally
```bash
python -m streamlit run app/streamlit_app.py
```
- With `MOTHERDUCK_TOKEN` set, the app reads from MotherDuck; otherwise from the local file. The sidebar shows which.
- For AI briefings and Ask Pulse, add `OPENROUTER_API_KEY` (and optionally `OPENROUTER_MODEL`) to `.streamlit/secrets.toml`.
  Without a key the app uses template briefings and example questions.
- Use `python -m streamlit` rather than `streamlit` so the app runs with the project's virtual environment.

## 4. Deploy (Streamlit Community Cloud, free)
1. Push the repo to GitHub. `secrets.toml` is git-ignored, so keys never leave your laptop.
2. In MotherDuck, create a second token of the **read-only (read scaling)** type for the app.
3. share.streamlit.io > Create app > pick the repo, branch `main`, main file `app/streamlit_app.py`.
4. Advanced settings > Secrets: paste `MOTHERDUCK_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`.
5. In OpenRouter, set a credit limit on the key used by the public app.

## Pages
| Page | Question it answers |
|---|---|
| Executive overview | Are members starting, staying, and getting value, and what does non-use cost? |
| Activation | How many members start, how fast, and who gets stuck? |
| Retention | Cohort heatmap, retention curves, and the first-week habit |
| Engagement & sessions | Status today, CRM status accuracy, module and session patterns |
| Coach outreach impact | Does the 48-hour welcome call work? Three estimates, honestly compared |
| Devices & billing | Faults by firmware, replacement downtime, returns, zero-use billing, denials |
| Care team call list | Who to call this week, why, and what to say (explainable risk model) |
| Recommendations | Six initiatives sized with the data, including care bundles, plus a measurement plan |
| AI briefing | The same data written for each team, with every number fact-checked |
| Ask Pulse | Plain-English questions to guarded, read-only SQL, explained |
| How it's built | Architecture, definitions, data notes |
