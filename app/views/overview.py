import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.facts import compute_facts, fd

c.page_header("Executive overview", "Are members starting, staying, and getting value, and what is it costing us when they don't?")

k = metrics.get("kpi").iloc[0]
F = fd(compute_facts())

r1 = st.columns(4)
r1[0].metric("Active members (last 7 days)", f"{k.active_now:,.0f}", f"{k.active_now - k.active_prev:+,.0f} vs Sep 30", border=True,
             help=metrics.DEFINITIONS["Engagement status"])
r1[1].metric("Activation, Jul to Sep", c.pct(k.activation_recent),
             f"{(k.activation_recent - k.activation_prior) * 100:+.1f} pts vs Apr to Jun", border=True, help=metrics.DEFINITIONS["Activated"])
r1[2].metric("Day-30 retention, Jul to Sep", c.pct(k.d30_recent),
             f"{(k.d30_recent - k.d30_prior) * 100:+.1f} pts vs Apr to Jun", border=True, help=metrics.DEFINITIONS["Day-30 retention"])
r1[3].metric("Program completion", c.pct(k.completion_rate), border=True, help=metrics.DEFINITIONS["Completed program"])
r2 = st.columns(4)
r2[0].metric("High-risk members", f"{k.high_risk:,.0f}", border=True, help=metrics.DEFINITIONS["Lapse risk"])
r2[1].metric("Idle headsets at home", f"{k.idle_headsets:,.0f}", border=True, help=metrics.DEFINITIONS["Idle headset"])
r2[2].metric("Zero-use billing, 90 days", c.money(k.zero_use_billed_90d),
             f"{k.zero_use_billed_90d / k.billed_90d:.0%} of billing", delta_color="inverse", border=True,
             help=metrics.DEFINITIONS["Zero-use rental month"])
r2[3].metric("Fault rate, firmware 4.2.0", F["fault_bad_fw"]["display"],
             f"{(F['fault_bad_fw']['value'] - F['fault_other_fw']['value']) * 100:+.0f} pts vs other firmware",
             delta_color="inverse", border=True)

st.subheader("What leadership should know")
st.markdown(f"""
1. **The first week decides who stays.** Members with 5+ sessions in week one are still active at day 30 at
   **{F['d30_week1_five']['display']}**, vs **{F['d30_week1_one']['display']}** for members with one session.
2. **The 48-hour welcome call works, but less than the raw numbers suggest.** Reached members activate
   {F['outreach_naive']['value'] * 100:.0f} points more often, but motivated members also pick up the phone. After the June SLA, activation
   rose **{F['outreach_sla']['value'] * 100:.0f} points** across all new members, which is the more trustworthy number.
3. **About a third of recent rental billing is for months with no use** ({F['zero_use_billed_90d']['display']} in 90 days).
   That is both an audit risk and a re-engagement opportunity.
4. **A bad firmware batch hurt members.** Firmware 4.2.0 failed at {F['fault_bad_fw']['display']}, and replacements in Feb to Mar
   took {F['downtime_slow']['display']} days on average.
""")

st.subheader("Growth and activation by delivery month")
mo = metrics.get("monthly")
mo = mo[mo.month < pd.Timestamp("2026-10-01")]
left, right = st.columns(2)
with left:
    st.markdown("**Headsets delivered per month**")
    fig = c.bar(mo, "month", "delivered", hover="%{x|%b %Y}: %{y:,} headsets<extra></extra>", height=280)
    fig.update_xaxes(tickformat="%b %y")
    c.show(fig, metrics.SQL["monthly"], key="ov_deliv")
with right:
    st.markdown("**Activation rate (first session within 14 days)**")
    fig = c.lines(mo, "month", "activation_rate", pct=True, height=280)
    fig.update_yaxes(range=[0.6, 0.95])
    fig.update_xaxes(tickformat="%b %y")
    c.add_band(fig, "2025-11-01", "2026-01-31", "Holiday surge")
    c.add_event(fig, "2026-06-01", "48h call SLA")
    c.show(fig, key="ov_act")

left, right = st.columns([3, 2])
with left:
    st.markdown("**Members using their headset each week**")
    wk = metrics.get("weekly_active")
    fig = c.lines(wk, "week", "active_members", height=280)
    fig.update_traces(mode="lines", hovertemplate="Week of %{x|%b %d}: %{y:,} members<extra></extra>")
    c.show(fig, metrics.SQL["weekly_active"], key="ov_wk")
with right:
    st.markdown("**Where members stand today**")
    sm = metrics.get("status_mix").set_index("status").reindex(c.STATUS_ORDER).dropna().reset_index()
    fig = c.bar(sm, "status", "members", color=[c.STATUS_COLORS[s] for s in sm.status], horizontal=True,
                text_fmt="{:,.0f}", hover="%{y}: %{x:,} members<extra></extra>", height=280)
    c.show(fig, metrics.SQL["status_mix"], key="ov_status")

st.caption("Churned includes members who returned their headset after stopping. Completed members finished the 8-week program and returned the headset.")
