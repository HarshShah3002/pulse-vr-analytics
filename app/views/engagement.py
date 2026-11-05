import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.facts import compute_facts, fd

c.page_header("Engagement & sessions", "How are members using the headset, and can we trust the engagement status in the CRM?")
F = fd(compute_facts())

left, right = st.columns(2)
with left:
    st.markdown("**Engagement status today**")
    sm = metrics.get("status_mix").set_index("status").reindex(c.STATUS_ORDER).dropna().reset_index()
    sm["share"] = sm.members / sm.members.sum()
    fig = c.bar(sm, "status", "members", color=[c.STATUS_COLORS[s] for s in sm.status], horizontal=True,
                height=300)
    fig.update_traces(text=[f"{m:,.0f} ({s:.0%})" for m, s in zip(sm.members, sm.share)],
                      hovertemplate="%{y}: %{x:,} members<extra></extra>")
    fig.update_xaxes(range=[0, sm.members.max() * 1.25])
    c.show(fig, metrics.SQL["status_mix"], key="eng_status")
with right:
    st.markdown("**Days since last session, members with a headset at home**")
    rc = metrics.get("recency")
    colors = [c.STATUS["good"], c.STATUS["warning"], c.STATUS["warning"], c.STATUS["serious"], c.STATUS["serious"],
              c.STATUS["critical"], c.STATUS["critical"]][: len(rc)]
    fig = c.bar(rc, "bucket", "members", color=colors, text_fmt="{:,.0f}", height=300,
                hover="%{x} days: %{y:,} members<extra></extra>")
    fig.update_xaxes(type="category", title="Days since last session")
    c.show(fig, metrics.SQL["recency"], key="eng_recency")
    st.caption("Everyone right of 30 days still has a headset at home and is likely still being billed.")

st.subheader("Can we trust the CRM status?")
c.insight(f"Headsets without home wifi save sessions and upload them days later. At month end, the CRM showed "
          f"<b>{F['crm_false_alarm_nowifi']['display']}</b> of truly active members without wifi as not active, "
          f"so coaches were calling people who were doing fine.")
crm = metrics.get("crm_accuracy")
left, right = st.columns([2, 3])
with left:
    fig = c.bar(crm, "wifi", "false_alarm_rate", color=[c.SERIES[1] if w == "No home wifi" else c.SERIES[0] for w in crm.wifi], pct=True, text_fmt="{:.0%}", height=260)
    fig.update_traces(customdata=crm.truly_active,
                      hovertemplate="%{x}<br>%{y:.1%} wrongly shown as inactive<br>%{customdata:,} active member-months<extra></extra>")
    fig.update_yaxes(range=[0, 0.6])
    c.show(fig, metrics.SQL["crm_accuracy"], key="eng_crm")
with right:
    st.markdown("""
**How this was measured:** at every month end since Jul 2025, compare the status the CRM could see (only synced sessions)
with the status we know now (every session, by headset clock).

**Fix options**
- Check the headset's last sync time before flagging a member at risk.
- Give offline members a longer at-risk window, or a weekly sync reminder.
- Prioritize wifi or a cellular hotspot for members flagged "No home wifi" at intake.
""")

st.subheader("How sessions are used")
mods = metrics.get("modules")
st.markdown("**Module performance**")
st.dataframe(
    mods[["module", "sessions", "members", "median_minutes", "completion_rate", "avg_pain_relief"]],
    hide_index=True, width="stretch",
    column_config={
        "module": "Module",
        "sessions": st.column_config.NumberColumn("Sessions", format="%d"),
        "members": st.column_config.NumberColumn("Members", format="%d"),
        "median_minutes": st.column_config.NumberColumn("Median minutes", format="%.1f"),
        "completion_rate": st.column_config.ProgressColumn("Finished the session", format="percent", min_value=0, max_value=1),
        "avg_pain_relief": st.column_config.NumberColumn("Avg pain relief (0 to 10)", format="%.2f",
                                                         help="Self-reported pain before minus after the session, pain members only"),
    },
)
c.show_sql(metrics.SQL["modules"])

left, right = st.columns(2)
with left:
    st.markdown("**Session length**")
    dh = metrics.get("duration_hist")
    dh["label"] = [f"{m}+" if m == 20 else f"{m}-{m + 2}" for m in dh.minutes_from]
    fig = c.bar(dh, "label", "sessions", height=280, hover="%{x} min: %{y:,} sessions<extra></extra>")
    fig.update_xaxes(type="category", title="Minutes")
    c.show(fig, metrics.SQL["duration_hist"], key="eng_dur")
with right:
    st.markdown("**When members use it**")
    td = metrics.get("time_of_day")
    td["share"] = td.sessions / td.sessions.sum()
    fig = c.bar(td, "time_of_day", "share", pct=True, text_fmt="{:.0%}", height=280,
                hover="%{x}: %{y:.1%} of sessions<extra></extra>")
    c.show(fig, metrics.SQL["time_of_day"], key="eng_tod")
    st.caption("Morning and evening peaks: good windows for coach calls and in-app reminders.")
