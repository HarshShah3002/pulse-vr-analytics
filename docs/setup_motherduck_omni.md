# Setup: MotherDuck + Omni

Total time: about 45 minutes. Do steps 1 to 3 before starting the Omni trial so no trial days are wasted.

## 1. Build locally (5 min)
```bash
pip install duckdb faker pandas numpy pyyaml
python generator/generate_data.py      # writes data/raw/*.csv (about 7 seconds)
python build_warehouse.py              # builds warehouse/pulse.duckdb: raw -> staging -> marts
python validation/findings_check.py    # optional: prints the headline numbers
```

## 2. Create a MotherDuck account (5 min)
1. Sign up at motherduck.com (free plan is enough; it stays after the trial).
2. Settings > Access Tokens > create a **Read/Write** token. Copy it.

## 3. Load the warehouse into MotherDuck (2 min)
```bash
export MOTHERDUCK_TOKEN="paste-token-here"      # Windows PowerShell: $env:MOTHERDUCK_TOKEN="..."
python build_warehouse.py --motherduck
```
This creates a database called `pulse` with schemas `raw`, `staging`, `marts`. Check it in the MotherDuck UI.

## 4. Start the Omni trial and connect (10 min)
1. Start the free trial at omni.co.
2. Settings > Connections > Add Connection > **MotherDuck**.
   - Database: `pulse`
   - Token: the same Read/Write token
3. Under the connection, include the `marts` schema (you can exclude `raw` and `staging` so the AI only sees clean tables).

## 5. Paste in the semantic model (20 min)
Open the **Model IDE** (Develop > model for the MotherDuck connection). Omni will already have auto-generated a view for each table.

1. **View names.** Omni names schema views like `marts__dim_members`. If yours differ, find and replace `marts__` in the files in `omni/`.
2. **Views.** For each file in `omni/views/`, open the matching view in the IDE and replace its contents with the file. Keep `schema:` and `table_name:` matching what Omni generated.
3. **Relationships.** Paste `omni/relationships.yaml` into the relationships file.
4. **Model.** Paste the `ai_context` block from `omni/model.yaml` into the model file.
5. **Topics.** Create a topic for each file in `omni/topics/` (file name = topic name) and paste the contents.
6. Click **Validate**. If Omni flags a parameter, the Modeling Agent in the IDE can fix syntax for you; describe the error to it.
7. Promote the branch to the shared model.

## 6. Test the AI before building dashboards
Ask the Omni Agent these, one per topic, and check the answers against `validation/findings_check.py`:
- "How has activation changed since the 48-hour welcome call SLA?"
- "Does first-week usage predict who stays?"
- "Show me the cohort retention heatmap"
- "Are some headsets failing more than others?"
- "How much are we billing for headsets nobody is using?"
- "Can we trust the engagement status in the CRM?"

If an answer is off, improve the `ai_context`, `synonyms` or `sample_queries` for that topic and ask again. Keep a short log of before/after; it is a great interview story.

## 7. Before the trial ends
- Commit all model files to GitHub (Omni supports git sync; otherwise copy the YAML from the IDE).
- Record the walkthrough video and take screenshots of each dashboard.
