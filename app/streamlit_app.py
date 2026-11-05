"""Pulse: engagement intelligence for an at-home VR therapy program. Run: streamlit run app/streamlit_app.py"""
import streamlit as st

from lib import ai
from lib.charts import CSS
from lib.db import AS_OF_LABEL, source_label

st.set_page_config(page_title="Pulse · VR Engagement Analytics", page_icon=":material/monitor_heart:", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

pages = {
    "Business": [
        st.Page("views/overview.py", title="Executive overview", icon=":material/dashboard:", default=True),
        st.Page("views/activation.py", title="Activation", icon=":material/rocket_launch:"),
        st.Page("views/retention.py", title="Retention", icon=":material/grid_on:"),
        st.Page("views/engagement.py", title="Engagement & sessions", icon=":material/monitor_heart:"),
    ],
    "Operations": [
        st.Page("views/outreach.py", title="Coach outreach impact", icon=":material/support_agent:"),
        st.Page("views/operations.py", title="Devices & billing", icon=":material/inventory_2:"),
        st.Page("views/call_list.py", title="Care team call list", icon=":material/call:"),
    ],
    "Plan": [
        st.Page("views/recommendations.py", title="Recommendations", icon=":material/lightbulb:"),
    ],
    "AI": [
        st.Page("views/briefing.py", title="AI briefing", icon=":material/auto_awesome:"),
        st.Page("views/ask.py", title="Ask Pulse", icon=":material/forum:"),
    ],
    "About": [
        st.Page("views/about.py", title="How it's built", icon=":material/account_tree:"),
    ],
}

with st.sidebar:
    st.markdown("### Pulse")
    st.caption("Engagement intelligence for an at-home VR therapy program")
    st.markdown(
        f"<span class='pulse-tag'>Source: {source_label()}</span><br>"
        f"<span class='pulse-tag'>Data as of {AS_OF_LABEL}</span><br>"
        f"<span class='pulse-tag'>AI: {'OpenRouter · ' + ai.model_name() if ai.api_key() else 'template mode (no key)'}</span>",
        unsafe_allow_html=True,
    )
    st.caption("All data is simulated for a fictional company, Lumora Health.")

st.navigation(pages).run()
