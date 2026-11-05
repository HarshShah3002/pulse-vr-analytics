import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.facts import compute_facts, fd

c.page_header("Devices & billing", "Are headsets reliable, why do they come back, and what are we billing for unused equipment?")
F = fd(compute_facts())

tab_dev, tab_ret, tab_bill = st.tabs(["Device reliability", "Returns", "Billing & idle headsets"])

with tab_dev:
    c.insight(f"Firmware 4.2.0 (shipped Jan to Apr 2026) failed at <b>{F['fault_bad_fw']['display']}</b>, vs "
              f"{F['fault_other_fw']['display']} for other versions. Replacements in Feb to Mar took "
              f"<b>{F['downtime_slow']['display']} days</b>, vs {F['downtime_normal']['display']} in other months.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Fault rate by firmware version**")
        fw = metrics.get("fault_by_firmware")
        fig = c.bar(fw, "firmware_version", "fault_rate", pct=True, text_fmt="{:.1%}", height=300,
                    color=[c.STATUS["critical"] if v == "4.2.0" else c.SERIES[0] for v in fw.firmware_version])
        fig.update_traces(customdata=fw.shipped, hovertemplate="Firmware %{x}<br>%{y:.1%} faulty<br>%{customdata:,} shipped<extra></extra>")
        fig.update_xaxes(type="category")
        c.show(fig, metrics.SQL["fault_by_firmware"], key="ops_fw")
    with right:
        st.markdown("**Days without a working headset after a fault**")
        tr = metrics.get("replacement_turnaround")
        fig = c.bar(tr, "month", "avg_days_without_device", height=300,
                    color=[c.STATUS["serious"] if v > 10 else c.SERIES[0] for v in tr.avg_days_without_device])
        fig.update_traces(customdata=tr.replacements,
                          hovertemplate="%{x|%b %Y}<br>%{y:.1f} days on average<br>%{customdata} replacements<extra></extra>")
        fig.update_xaxes(tickformat="%b %y")
        c.show(fig, metrics.SQL["replacement_turnaround"], key="ops_turn")
    st.markdown("**Day-30 retention by first headset firmware**")
    d30 = metrics.get("d30_by_firmware")
    fig = c.bar(d30, "firmware_version", "d30", pct=True, text_fmt="{:.0%}", height=240, horizontal=True,
                color=[c.STATUS["critical"] if v == "4.2.0" else c.SERIES[0] for v in d30.firmware_version])
    fig.update_xaxes(range=[0, 1])
    c.show(fig, metrics.SQL["d30_by_firmware"], key="ops_fwd30")
    bad, good = d30[d30.firmware_version == "4.2.0"].d30.iloc[0], d30[d30.firmware_version != "4.2.0"]
    good_rate = (good.d30 * good.members).sum() / good.members.sum()
    st.caption(f"Members who got the faulty batch stayed at day 30 at {bad:.0%}, vs {good_rate:.0%} for other firmware. "
               "A small gap overall, because most members never had a fault; for those who did, see the downtime chart.")

with tab_ret:
    rr = metrics.get("return_reasons")
    cat_color = {"Healthy exit": c.SERIES[0], "Avoidable": c.SERIES[1], "Outside our control": c.NEUTRAL}
    c.insight(f"<b>{F['avoidable_return_share']['display']}</b> of returned headsets were avoidable exits: members who stopped "
              "using it, never started, felt discomfort, or had device issues.")
    fig = c.bar(rr, "return_reason", "headsets", horizontal=True, text_fmt="{:,.0f}", height=360,
                color=[cat_color[x] for x in rr.category])
    fig.update_traces(customdata=rr.category, hovertemplate="%{y}<br>%{x:,} headsets<br>%{customdata}<extra></extra>")
    fig.update_xaxes(range=[0, rr.headsets.max() * 1.15])
    c.show(fig, metrics.SQL["return_reasons"], key="ops_returns")
    st.markdown("<span class='pulse-tag' style='background:#2a78d6;color:#fff'>Healthy exit</span>"
                "<span class='pulse-tag' style='background:#eb6834;color:#fff'>Avoidable</span>"
                "<span class='pulse-tag'>Outside our control</span>", unsafe_allow_html=True)

with tab_bill:
    c.insight(f"In the last 90 days, <b>{F['zero_use_billed_90d']['display']}</b> ({F['zero_use_share_90d']['display']} of rental "
              f"billing) was for months with no sessions. {F['idle_headsets']['display']} headsets are idle at home right now.")
    bm = metrics.get("billing_monthly")
    left, right = st.columns(2)
    with left:
        st.markdown("**Share of billed rental months with zero use**")
        fig = c.lines(bm, "month", "zero_use_share", pct=True, height=300)
        fig.update_xaxes(tickformat="%b %y")
        fig.update_yaxes(range=[0, 0.6])
        c.add_event(fig, "2026-06-01", "Faster retrieval sweeps")
        c.show(fig, metrics.SQL["billing_monthly"], key="ops_zero")
    with right:
        st.markdown("**Idle headsets at home now, by how long they've been idle**")
        ib = metrics.get("idle_by_age")
        order = ["Never used", "31 to 45 days idle", "46 to 90 days idle", "90+ days idle"]
        ib = ib.set_index("bucket").reindex(order).dropna().reset_index()
        fig = c.bar(ib, "bucket", "headsets", text_fmt="{:,.0f}", height=300,
                    color=[c.NEUTRAL, c.STATUS["warning"], c.STATUS["serious"], c.STATUS["critical"]][: len(ib)])
        fig.update_xaxes(type="category")
        c.show(fig, metrics.SQL["idle_by_age"], key="ops_idle")
    left, right = st.columns(2)
    with left:
        st.markdown("**Rental billed vs collected per month**")
        long = pd.concat([bm[["month"]].assign(metric="Billed", value=bm.billed_usd),
                          bm[["month"]].assign(metric="Collected", value=bm.paid_usd)])
        fig = c.lines(long, "month", "value", group="metric", height=300)
        fig.update_traces(hovertemplate="%{fullData.name}: $%{y:,.0f}<extra></extra>")
        fig.update_yaxes(tickprefix="$", tickformat=",.0s")
        fig.update_xaxes(tickformat="%b %y")
        c.show(fig, key="ops_billed")
        st.caption("Recent months look low on collections because claims are still pending.")
    with right:
        st.markdown("**Claim denial rate by health plan**")
        dn = metrics.get("denials_by_plan")
        top = dn.denial_rate.max()
        fig = c.bar(dn, "plan", "denial_rate", horizontal=True, pct=True, text_fmt="{:.1%}", height=300,
                    color=[c.SERIES[1] if v == top else c.SERIES[0] for v in dn.denial_rate])
        fig.update_traces(customdata=dn.decided_claims, hovertemplate="%{y}<br>%{x:.1%} denied<br>%{customdata:,} decided claims<extra></extra>")
        fig.update_xaxes(range=[0, top * 1.3])
        c.show(fig, metrics.SQL["denials_by_plan"], key="ops_denials")
