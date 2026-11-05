import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics

c.page_header("Activation", "How many members actually start using their headset, how fast, and who gets stuck?")

fn = metrics.get("funnel")
fn["share_of_referred"] = fn.members / fn.members.iloc[0]
fn["step_conversion"] = fn.members / fn.members.shift(1)
deliv = fn.loc[fn.stage == "Headset delivered", "members"].iloc[0]
act = fn.loc[fn.stage == "Activated within 14 days", "members"].iloc[0]
c.insight(f"Of members whose headset was delivered, <b>{act / deliv:.0%}</b> started within 14 days. "
          f"The biggest single drop after that is building a habit in week one.")

st.markdown("**Member journey, referrals through Jun 30 2026** (every stage has had time to happen)")
ramp = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7"]
fig = go.Figure(go.Bar(
    y=fn.stage, x=fn.members, orientation="h", marker=dict(color=ramp, line=dict(width=0)),
    text=[f"{m:,}  ·  {s:.0%} of referred" for m, s in zip(fn.members, fn.share_of_referred)],
    textposition="outside", cliponaxis=False, textfont=dict(color=c.INK_2),
    customdata=fn.step_conversion,
    hovertemplate="%{y}<br>%{x:,} members<br>%{customdata:.0%} of previous step<extra></extra>",
))
c.style(fig, height=360, legend=False)
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(showgrid=True, range=[0, fn.members.max() * 1.35])
c.show(fig, metrics.SQL["funnel"], key="act_funnel")

left, right = st.columns(2)
with left:
    st.markdown("**Days from delivery to first session**")
    ds_all = metrics.get("days_to_start")
    never = ds_all[ds_all.days == "Never"].members.sum()
    ds = ds_all[ds_all.days != "Never"]
    colors = [c.SERIES[0] if d != "15+" else c.NEUTRAL for d in ds.days]
    fig = c.bar(ds, "days", "members", color=colors, hover="Day %{x}: %{y:,} members<extra></extra>", height=300)
    fig.update_xaxes(type="category", title="Days after delivery")
    c.show(fig, metrics.SQL["days_to_start"], key="act_days")
    total = ds_all.members.sum()
    same_week = ds[ds.sort_key <= 6].members.sum() / total
    st.caption(f"{same_week:.0%} of delivered members start within their first week. The gray bar is members who started "
               f"after day 14. Not shown: {never:,} members ({never / total:.0%}) who never started.")
with right:
    st.markdown("**Activation rate and 48-hour welcome calls by month**")
    mo = metrics.get("monthly")
    mo = mo[mo.month < pd.Timestamp("2026-10-01")]
    long = pd.concat([
        mo[["month"]].assign(metric="Activation rate", value=mo.activation_rate),
        mo[["month"]].assign(metric="Welcome call attempted within 48h", value=mo.attempted_48h_rate),
    ])
    fig = c.lines(long, "month", "value", group="metric", pct=True, height=300)
    fig.update_xaxes(tickformat="%b %y")
    c.add_band(fig, "2025-11-01", "2026-01-31", "Holiday surge")
    c.add_event(fig, "2026-06-01", "48h SLA")
    c.show(fig, metrics.SQL["monthly"], key="act_monthly")
    st.caption("When coaches were stretched over the holidays, fewer welcome calls happened in 48 hours. After the June SLA, almost every new member got one.")

st.subheader("Who gets stuck?")
seg = st.selectbox("Compare activation by", list(metrics.SEGMENTS), index=1, key="act_seg")
df, sql = metrics.by_segment("activation", seg)
overall = act / deliv
colors = [c.SERIES[0] if v >= overall else c.SERIES[1] for v in df.activation_rate]
fig = c.bar(df, "segment", "activation_rate", color=colors, horizontal=True, pct=True,
            text_fmt="{:.0%}", height=max(220, 46 * len(df)),
            hover="%{y}: %{x:.1%}<extra></extra>")
fig.update_traces(customdata=df.members, hovertemplate="%{y}<br>Activation %{x:.1%}<br>%{customdata:,} members<extra></extra>")
fig.add_vline(x=overall, line=dict(color=c.MUTED, dash="dot", width=1))
fig.update_xaxes(range=[0, 1.08])
c.show(fig, sql, key="act_seg_chart")
st.caption(f"Orange bars are below the overall activation rate ({overall:.0%}, dotted line). Groups under 30 members are hidden.")
