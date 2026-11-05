import streamlit as st

from lib import ai
from lib import charts as c
from lib.facts import compute_facts

c.page_header("AI briefing", "The same data, explained for each team in plain language, with every number checked against the warehouse.")

facts = compute_facts()
has_key = ai.api_key() is not None

audience = st.radio("Who is this for?", list(ai.AUDIENCES), horizontal=True, key="brief_aud")
st.caption(ai.AUDIENCES[audience])

state_key = f"brief_{audience}"
col_a, col_b = st.columns([1, 3])
with col_a:
    generate = st.button("Write briefing with AI" if has_key else "Show briefing", type="primary", width="stretch")
with col_b:
    if not has_key:
        st.caption("No OpenRouter key configured, so this uses the built-in template. Add OPENROUTER_API_KEY to secrets for AI-written briefings.")

if generate:
    if has_key:
        with st.spinner("Writing the briefing..."):
            try:
                text = ai.chat(ai.briefing_messages(audience, facts))
                st.session_state[state_key] = (text, "AI")
            except Exception as e:
                st.session_state[state_key] = (ai.template_briefing(audience, facts), f"Template (AI call failed: {e})")
    else:
        st.session_state[state_key] = (ai.template_briefing(audience, facts), "Template")

if state_key in st.session_state:
    text, mode = st.session_state[state_key]
    checks = ai.fact_check(text, ai.allowed_from_facts(facts))
    ok = sum(ch["verified"] for ch in checks)
    with st.container(border=True):
        st.markdown(text)
    if checks:
        if ok == len(checks):
            st.success(f"Fact check: all {len(checks)} numbers match the data.", icon=":material/verified:")
        else:
            bad = ", ".join(ch["number"] for ch in checks if not ch["verified"])
            st.warning(f"Fact check: {ok} of {len(checks)} numbers match the data. Not found in the fact sheet: {bad}. "
                       "Review before sharing.", icon=":material/warning:")
    st.caption(f"Written by: {mode}" + (f" · model {ai.model_name()}" if mode == "AI" else ""))
    st.download_button("Download as Markdown", text.encode(), file_name=f"pulse_briefing_{audience.lower().replace(' ', '_')}.md")

with st.expander("The fact sheet the AI is allowed to use"):
    st.markdown("The AI never sees raw member data. It only gets these numbers, computed from the warehouse, plus the metric "
                "definitions. The fact check then confirms every number it wrote appears here.")
    st.dataframe([{"Fact": f["label"], "Value": f["display"]} for f in facts], hide_index=True, width="stretch")
