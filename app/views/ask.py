import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai
from lib import charts as c
from lib.db import run
from lib.facts import compute_facts

c.page_header("Ask Pulse", "Ask a business question in plain English. Pulse writes the SQL, runs it on the warehouse, and explains the answer.")
has_key = ai.api_key() is not None


@st.cache_data(ttl=3600, show_spinner=False)
def cached_sql(question: str) -> str:
    return ai.question_to_sql(question)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_big_picture(question: str) -> str:
    return ai.chat(ai.big_picture_messages(question, compute_facts()))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_explain(question: str, sql: str, df: pd.DataFrame) -> str:
    return ai.explain_result(question, sql, df)


def auto_chart(df: pd.DataFrame):
    if df.empty or len(df.columns) < 2 or len(df) > 40:
        return None
    label = df.columns[0]
    nums = [col for col in df.columns[1:] if pd.api.types.is_numeric_dtype(df[col])]
    if not nums:
        return None
    rate = next((n for n in nums if df[n].between(0, 1).all() and ("rate" in n or "retention" in n or "share" in n)), None)
    y = rate or nums[0]
    d = df.copy()
    d[label] = d[label].astype(str)
    if pd.api.types.is_datetime64_any_dtype(df[label]):
        return c.lines(df, label, y, pct=bool(rate), height=300)
    fig = c.bar(d, label, y, horizontal=True, pct=bool(rate), text_fmt="{:.0%}" if rate else "{:,.0f}",
                height=max(220, 40 * len(d)))
    if rate:
        fig.update_xaxes(range=[0, 1.1])
    return fig


def show_answer(question: str, sql: str, explain: bool):
    err = ai.check_sql(sql)
    if err:
        st.error(f"Pulse wrote a query it isn't allowed to run: {err}")
        st.code(sql, language="sql")
        return
    try:
        df = run(f"select * from ({sql}) limit 500")
    except Exception as e:
        st.error(f"The query failed: {e}")
        st.code(sql, language="sql")
        return
    with st.container(border=True):
        if explain:
            with st.spinner("Explaining the result..."):
                try:
                    text = cached_explain(question, sql, df)
                    st.markdown(text)
                    checks = ai.fact_check(text, ai.allowed_from_frame(df))
                    ok = sum(ch["verified"] for ch in checks)
                    if checks:
                        st.caption(f"Fact check: {ok} of {len(checks)} numbers in this answer appear in the query result.")
                except Exception as e:
                    st.caption(f"Could not get an explanation: {e}")
        fig = auto_chart(df)
        if fig is not None:
            c.show(fig, key=f"ask_{abs(hash(sql))}")
        cfg = {}
        for col in df.columns:
            label = col.replace("_", " ").capitalize()
            if pd.api.types.is_numeric_dtype(df[col]) and df[col].dropna().between(0, 1).all() and \
                    any(w in col for w in ("rate", "retention", "share", "pct")):
                cfg[col] = st.column_config.NumberColumn(label, format="percent")
            elif pd.api.types.is_float_dtype(df[col]):
                cfg[col] = st.column_config.NumberColumn(label, format="%.2f")
            else:
                cfg[col] = st.column_config.Column(label)
        st.dataframe(df, hide_index=True, width="stretch", column_config=cfg)
    c.show_sql(sql)


if has_key:
    q = st.text_input("Your question", placeholder="e.g. Which referral source has the best day-30 retention?")
    st.caption("Try: *Do members with comorbid anxiety use mindfulness more?* · *Which coaches have the most high-risk members?* · "
               "*How did zero-use billing change after June 2026?*")
    if q:
        with st.spinner("Writing SQL..."):
            try:
                sql = cached_sql(q)
            except Exception as e:
                st.error(f"AI call failed: {e}")
                st.stop()
        if sql is None:
            st.info("This is a big-picture question, so Pulse answered it from the key business metrics "
                    "instead of a single query.", icon=":material/lightbulb:")
            with st.spinner("Thinking it through..."):
                try:
                    text = cached_big_picture(q)
                except Exception as e:
                    st.error(f"AI call failed: {e}")
                    st.stop()
            checks = ai.fact_check(text, ai.allowed_from_facts(compute_facts()))
            with st.container(border=True):
                st.markdown(text)
                if checks:
                    ok = sum(ch["verified"] for ch in checks)
                    st.caption(f"Fact check: {ok} of {len(checks)} numbers match the data.")
            st.caption("For sized initiatives see **Recommendations**; for team-specific summaries see **AI briefing**.")
        else:
            show_answer(q, sql, explain=True)
    st.divider()

st.markdown("**Example questions**" + ("" if has_key else " (add an OpenRouter key to ask your own)"))
choice = st.selectbox("Pick a question", list(ai.EXAMPLES), label_visibility="collapsed")
show_answer(choice, ai.EXAMPLES[choice].strip(), explain=has_key)

with st.expander("Guardrails"):
    st.markdown("""
- Only single, read-only `SELECT` queries on the `marts` schema run. Writes, file reads, and settings changes are blocked.
- Personal details (names, emails, phone numbers, birth dates) are never returned.
- In the deployed app, the warehouse connection uses a **read-only** MotherDuck token.
- The AI sees the table schema and metric definitions, plus at most 40 result rows when explaining. It never sees raw member records.
""")
