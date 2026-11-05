import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.facts import compute_facts, fd

c.page_header("Retention", "Once members start, how long do they keep using the headset, and what predicts who stays?")
F = fd(compute_facts())

c.insight(f"Members with <b>5+ sessions in week one</b> are still active at day 30 at <b>{F['d30_week1_five']['display']}</b>, "
          f"vs <b>{F['d30_week1_one']['display']}</b> with one session. Even after adjusting for member profile, a 3+ session "
          f"first week is linked to <b>{F['habit_effect_adjusted']['display']}</b> of day-30 retention.")

st.markdown("**Weekly retention by start cohort** (share of each month's new starters who used the headset that week)")
hm = metrics.get("cohort_heatmap")
piv = hm.pivot(index="cohort", columns="week", values="retention").sort_index()
size = hm[hm.week == 0].set_index("cohort").members
labels = [f"{d:%b %Y} ({size.get(d, 0):,})" for d in piv.index]
text = [[("" if pd.isna(v) else f"{v:.0%}") for v in row] for row in piv.values]
fig = go.Figure(go.Heatmap(
    z=piv.values, x=[f"W{w}" for w in piv.columns], y=labels, text=text, texttemplate="%{text}",
    textfont=dict(size=11), colorscale=[[i / (len(c.BLUE_RAMP) - 1), col] for i, col in enumerate(c.BLUE_RAMP)],
    zmin=0.2, zmax=1, xgap=2, ygap=2, colorbar=dict(tickformat=".0%", thickness=10, outlinewidth=0),
    hovertemplate="%{y}<br>%{x}: %{z:.1%} active<extra></extra>",
))
c.style(fig, height=520, legend=False)
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(side="top", title="Weeks since first session")
c.show(fig, metrics.SQL["cohort_heatmap"], key="ret_heat")
st.caption("Blank cells have not happened yet for the whole cohort. The program is 8 weeks; weeks 9 to 12 show maintenance use. "
           "Row labels show how many members started that month.")

left, right = st.columns(2)
with left:
    st.markdown("**Day-30 retention by first-week sessions**")
    w1 = metrics.get("d30_by_week1")
    fig = c.bar(w1, "bucket", "d30", pct=True, text_fmt="{:.0%}", height=300,
                color=[c.SERIES[1], c.SERIES[1], c.SERIES[0], c.SERIES[0]])
    fig.update_traces(customdata=w1.members, hovertemplate="%{x}<br>Day-30 retention %{y:.1%}<br>%{customdata:,} members<extra></extra>")
    fig.update_yaxes(range=[0, 1])
    c.show(fig, metrics.SQL["d30_by_week1"], key="ret_w1")
    st.caption("Orange: fewer than 3 sessions in week one. This is the single strongest early signal in the data.")
with right:
    st.markdown("**Day-30 retention by average session length in week one**")
    wm = metrics.get("d30_by_week1_minutes")
    best = wm.d30.max()
    fig = c.bar(wm, "bucket", "d30", pct=True, text_fmt="{:.0%}", height=300,
                color=[c.SERIES[0] if v == best else c.NEUTRAL for v in wm.d30])
    fig.update_traces(customdata=wm.members, hovertemplate="%{x}<br>Day-30 retention %{y:.1%}<br>%{customdata:,} members<extra></extra>")
    fig.update_yaxes(range=[0, 1])
    c.show(fig, metrics.SQL["d30_by_week1_minutes"], key="ret_min")
    st.caption("Longer is not always better: moderate sessions retain best. Very short sessions suggest trouble getting started; "
               "very long ones may mean fatigue. How often members use it matters more than session length.")

st.subheader("Retention curves by group")
seg = st.selectbox("Split curves by", metrics.CURVE_SEGMENTS, index=0, key="ret_seg")
df, sql = metrics.by_segment("curve", seg)
order = None
if seg == "Week-1 sessions":
    order = ["1 session", "2 sessions", "3 to 4 sessions", "5+ sessions"]
fig = c.lines(df, "week", "retention", group="segment", pct=True, height=360, order=order)
fig.update_xaxes(title="Weeks since first session", dtick=1)
fig.update_yaxes(range=[0, 1.02])
c.show(fig, sql, key="ret_curve")
st.caption("Each point is the share of members in that group who used the headset during that week. Groups under 30 members are hidden.")

st.subheader("Is the week-one link real, or just motivated members?")
eff = metrics.get("effects")
e = eff[eff.analysis == "week1_habit"]
cols = st.columns(len(e))
for col, (_, r) in zip(cols, e.iterrows()):
    col.metric(r.method, f"{r.estimate * 100:+.0f} pts", f"95% range {r.ci_low * 100:+.0f} to {r.ci_high * 100:+.0f} pts",
               delta_color="off", border=True)
st.caption("Adjusting for referral source, tech comfort, age, insurance, condition, location and delivery month barely changes the gap. "
           "Unmeasured motivation could still play a part, so the best proof would be a test: nudge half of new members toward "
           "3 sessions in week one and compare.")
