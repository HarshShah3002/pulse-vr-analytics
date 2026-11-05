import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.facts import compute_facts, fd

c.page_header("Coach outreach impact", "Does reaching members within 48 hours of delivery actually make them more likely to start?")
F = fd(compute_facts())

c.insight(f"Yes, but by less than the raw numbers suggest. Reached members activate {F['outreach_naive']['value'] * 100:.0f} points more often, "
          f"partly because motivated members answer the phone. The cleanest evidence is the June 2026 SLA: welcome calls within 48 hours "
          f"went from {F['attempt48_pre']['display']} to {F['attempt48_post']['display']} of new members, and activation rose "
          f"<b>{F['outreach_sla']['value'] * 100:.0f} points</b> across everyone.")

eff = metrics.get("effects")
e = eff[eff.analysis == "outreach_48h"].reset_index(drop=True)
labels = ["Raw comparison<br>(reached vs not)", "Adjusted for<br>member profile", "Before vs after<br>the 48h SLA"]
colors = [c.NEUTRAL, c.SERIES[6], c.SERIES[0]]
st.markdown("**Three ways to estimate the effect on activation** (percentage points, with 95% range)")
fig = go.Figure()
for i, r in e.iterrows():
    fig.add_trace(go.Scatter(
        x=[r.estimate], y=[labels[i]], mode="markers",
        marker=dict(size=13, color=colors[i], line=dict(width=2, color="#fcfcfb")),
        error_x=dict(type="data", symmetric=False, array=[r.ci_high - r.estimate], arrayminus=[r.estimate - r.ci_low],
                     color=colors[i], thickness=2, width=6),
        hovertemplate=f"{r.method}<br>%{{x:+.1%}} (range {r.ci_low:+.1%} to {r.ci_high:+.1%})<br>{int(r.n):,} members<extra></extra>",
        showlegend=False,
    ))
    fig.add_annotation(x=r.ci_high, y=labels[i], text=f"<b>{r.estimate * 100:+.1f} pts</b>", showarrow=False, xanchor="left",
                       xshift=10, font=dict(color=c.INK, size=13))
c.style(fig, height=260, legend=False)
fig.update_xaxes(tickformat="+.0%", range=[-0.02, 0.3], zeroline=True, zerolinecolor=c.AXIS, showgrid=True)
fig.update_yaxes(autorange="reversed", showgrid=False)
c.show(fig, metrics.SQL["effects"], key="out_forest")

with st.expander("What each estimate means"):
    for _, r in e.iterrows():
        st.markdown(f"**{r.method}** ({int(r.n):,} members). {r.detail}. {r.caveat}")
    st.markdown("**Takeaway for planning:** budget for the before/after number (about "
                f"{F['outreach_sla']['display']} of activation across all new members), not the raw gap. "
                "To measure it precisely, randomize the order of welcome calls for a few weeks.")

left, right = st.columns(2)
with left:
    st.markdown("**What coaches spend their time on**")
    tm = metrics.get("touch_mix")
    order = ["Welcome", "Setup help", "Check-in", "Re-engagement nudge", "Device support", "Program completion"]
    fig = go.Figure()
    for i, t in enumerate(order):
        d = tm[tm.touch_type == t]
        fig.add_trace(go.Bar(x=d.month, y=d.touches, name=t, marker=dict(color=c.SERIES[i], line=dict(width=0)),
                             hovertemplate=f"{t}: %{{y:,}}<extra></extra>"))
    c.style(fig, height=330)
    fig.update_layout(barmode="stack", hovermode="x unified", bargap=0.25)
    fig.update_xaxes(tickformat="%b %y")
    c.show(fig, metrics.SQL["touch_mix"], key="out_mix")
with right:
    st.markdown("**How often a coach's call reaches the member**")
    rt = metrics.get("reach_by_type").dropna()
    rt = rt[rt.touch_type.isin(["Welcome", "Setup help", "Check-in", "Re-engagement nudge"])]
    fig = c.bar(rt, "touch_type", "call_reach_rate", horizontal=True, pct=True, text_fmt="{:.0%}", height=330)
    fig.update_traces(customdata=rt.calls, hovertemplate="%{y}<br>%{x:.1%} reached<br>%{customdata:,} calls<extra></extra>")
    fig.update_xaxes(range=[0, 1.1])
    c.show(fig, metrics.SQL["reach_by_type"], key="out_reach")
    low = rt.sort_values("call_reach_rate").iloc[0]
    st.caption(f"Calls coaches start themselves. {low.touch_type} calls connect least often ({low.call_reach_rate:.0%}). "
               "Text first, then call at the member's usual session time (mornings or evenings).")
