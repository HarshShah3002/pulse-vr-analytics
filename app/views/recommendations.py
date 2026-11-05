import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts as c
from lib import metrics
from lib.db import run

c.page_header("Recommendations", "What we should do next, sized with our own data, and how we'll know it worked.")


@st.cache_data(ttl=900, show_spinner=False)
def sizing() -> dict:
    one = lambda sql: run(sql).iloc[0].to_dict()
    s = {}
    s.update(one("""select count(*) / 3.0 as starters_per_month from marts.dim_members
                    where first_session_date between date '2026-07-01' and date '2026-09-30'"""))
    s.update(one("""select count(*) / 3.0 as deliveries_per_month from marts.dim_members
                    where delivery_date between date '2026-07-01' and date '2026-09-30'"""))
    s.update(one("""select avg((not hit_week1_habit)::int) as slow_start_share from marts.dim_members
                    where has_started and is_week1_matured and first_session_date >= date '2026-04-01'"""))
    s.update(one("""select avg((not has_started)::int) as never_start_share from marts.dim_members
                    where is_delivered and is_activation_matured and delivery_date >= date '2026-06-01'"""))
    s.update(one("""select sum(billed_amount_usd) filter (where is_zombie_month) / 3 as zero_use_usd_per_month
                    from marts.fct_rental_months where service_month between date '2026-07-01' and date '2026-09-01'"""))
    s.update(one("""select count(*) filter (where is_idle_headset_30d) as idle_headsets,
                           count(*) filter (where engagement_status = 'Active' and not has_home_wifi) as active_no_wifi,
                           count(*) filter (where engagement_status = 'Active') as active_now,
                           count(*) filter (where completed_program and headset_at_home) as completers_keeping,
                           count(*) filter (where completed_program and headset_at_home and days_since_last_session <= 30) as completers_active
                    from marts.dim_members"""))
    s.update(one("""select count(*) filter (where order_status = 'Replaced') as bad_fw_faults, count(*) as bad_fw_shipped
                    from marts.fct_orders where firmware_version = '4.2.0'"""))
    s.update(one("""select avg(n) as false_alarms_per_month from (
                      select snapshot_date, count(*) filter (where is_false_alarm) as n
                      from marts.fct_status_backtest where not has_home_wifi group by 1)"""))
    s.update(one("""select count(*) filter (where primary_condition <> 'Anxiety and stress' and has_comorbid_anxiety) as pain_with_anxiety,
                           count(*) filter (where primary_condition = 'Anxiety and stress') as anxiety_track,
                           count(*) filter (where primary_condition in ('Chronic low back pain', 'Chronic neck and joint pain')) as back_joint
                    from marts.dim_members where has_started"""))
    mods = run("""select m.has_comorbid_anxiety as comorbid,
                         avg((s.module in ('Mindfulness', 'Anxiety and Stress CBT'))::int) as mental_health_share
                  from marts.fct_sessions s join marts.dim_members m using (member_id)
                  where m.primary_condition <> 'Anxiety and stress' group by 1""").set_index("comorbid")["mental_health_share"]
    s["mh_share_comorbid"], s["mh_share_other"] = float(mods.loc[True]), float(mods.loc[False])
    eff = metrics.get("effects").set_index(["analysis", "method"])["estimate"]
    s["habit_effect"] = float(eff.loc[("week1_habit", "Adjusted for member profile")])
    s["sla_effect"] = float(eff.loc[("outreach_48h", "Before vs after 48h SLA (Jun 2026)")])
    return s


S = sizing()
slow_per_month = S["starters_per_month"] * S["slow_start_share"]
never_per_month = S["deliveries_per_month"] * S["never_start_share"]

c.insight(f"Three moves matter most: win the <b>first week</b> (about {never_per_month:.0f} members a month never start and "
          f"{slow_per_month:.0f} start slowly), stop <b>billing for unused headsets</b> (about {c.money(S['zero_use_usd_per_month'])} "
          f"a month), and make the <b>device experience reliable</b>. Bundles with therapy and physical care partners are the growth bet.")

rows = [
    ("1", "First-week activation program", "Care team + Product",
     f"~{never_per_month:.0f} never start and ~{slow_per_month:.0f} start slowly each month", "Medium", "Day-2 nudge and day-3 coach call pilot"),
    ("2", "Keep the 48-hour welcome call", "Care team",
     f"Activation +{S['sla_effect'] * 100:.0f} pts since the SLA (~{S['deliveries_per_month'] * S['sla_effect']:.0f} members/month)", "Low", "Weekly SLA report"),
    ("3", "Idle headset policy", "Operations + Billing",
     f"{S['idle_headsets']:,.0f} idle now; {c.money(S['zero_use_usd_per_month'])}/month billed for zero use", "Low", "Outreach at 14 days idle, pickup at 30"),
    ("4", "Device reliability guardrails", "Operations",
     f"{S['bad_fw_faults']:,.0f} faulty headsets from one firmware batch", "Medium", "Staged firmware rollout with a fault alert"),
    ("5", "Trustworthy engagement status", "Care team + Data",
     f"~{S['false_alarms_per_month']:.0f} false 'inactive' flags a month", "Low", "Use headset sync time in the status rule"),
    ("6", "Care bundles with partners", "Partnerships + Product",
     f"{S['pain_with_anxiety'] + S['anxiety_track']:,.0f} members with anxiety needs; {S['back_joint']:,.0f} with back and joint pain", "High", "90-day pilot with one health plan"),
]
st.markdown("| # | Recommendation | Owner | Size of the opportunity | Effort | First step |\n|---|---|---|---|---|---|\n"
            + "\n".join("| " + " | ".join(r) + " |" for r in rows))
st.write("")

tab1, tab2, tab3, tab4 = st.tabs(["Activate & retain", "Operations", "Bundles & partnerships", "How we'll measure"])

# ---------------------------------------------------------------- activate & retain
with tab1:
    st.subheader("1. First-week activation program")
    st.markdown(f"""
**What the data says.** About **{S['never_start_share']:.0%}** of recent deliveries never start (~{never_per_month:.0f} members a month),
and **{S['slow_start_share']:.0%}** of members who start do fewer than 3 sessions in week one (~{slow_per_month:.0f} a month).
Slow starters are far less likely to still be using the program at day 30, and the gap holds after adjusting for member profile
(about **{S['habit_effect'] * 100:.0f} points**).

**What to do**
- **Day 2:** in-headset prompt and a text if no session yet ("Try a 6-minute breathing session tonight").
- **Day 3:** coach call for members with 0 to 1 sessions, offering a guided first session over the phone.
- **Week one goal:** 3 short sessions of about 8 to 10 minutes, shown as a progress ring in the headset.
""")
    conv = st.slider("If the program moves this share of slow starters to 3+ sessions in week one:", 10, 60, 30, 5, format="%d%%")
    extra = slow_per_month * conv / 100 * S["habit_effect"]
    k = st.columns(3)
    k[0].metric("Slow starters per month", f"{slow_per_month:.0f}", border=True)
    k[1].metric("Moved to a 3+ session first week", f"{slow_per_month * conv / 100:.0f}", border=True)
    k[2].metric("Extra members still active at day 30", f"~{extra:.0f} / month", f"~{extra * 12:.0f} a year", delta_color="off", border=True)
    st.caption("Uses the adjusted week-one effect. Treat it as an estimate until an A/B test confirms it (see How we'll measure).")

    st.subheader("2. Keep the 48-hour welcome call")
    st.markdown(f"""
After the June 2026 SLA, activation rose about **{S['sla_effect'] * 100:.0f} points** across all new members, roughly
**{S['deliveries_per_month'] * S['sla_effect']:.0f} more members starting each month**. This is working: protect it with a weekly SLA
report and extra coach capacity planned ahead of holiday volume, when 48-hour calls dropped below 40% last year.
""")

# ---------------------------------------------------------------- operations
with tab2:
    st.subheader("3. Idle headset policy")
    st.markdown(f"""
**What the data says.** **{S['idle_headsets']:,.0f} headsets** sit at members' homes with no session in 30+ days, and about
**{c.money(S['zero_use_usd_per_month'])} a month** of rental is billed for months with no use. That is revenue a payer audit could
question, and equipment another member could be using.

**What to do**
- **14 days idle:** coach outreach with a reason-specific script (device, discomfort, motivation).
- **30 days idle:** offer a pause or a prepaid return label; stop billing at the return request.
- **Redeploy** refurbished headsets to new members instead of buying new ones.
""")
    cost = st.number_input("Assumed cost of a new headset kit, in dollars (replace with the real number)", 100, 2000, 500, 50)
    k = st.columns(3)
    k[0].metric("Idle headsets to recover", f"{S['idle_headsets']:,.0f}", border=True)
    k[1].metric("Equipment value to redeploy", c.money(S["idle_headsets"] * cost), border=True)
    k[2].metric("Zero-use billing per month", c.money(S["zero_use_usd_per_month"]), border=True)
    st.caption("Reducing zero-use billing lowers short-term revenue, but protects payer trust and audit standing. Present it to plans as a strength.")

    st.subheader("4. Device reliability guardrails")
    st.markdown(f"""
**What the data says.** Firmware 4.2.0 shipped on **{S['bad_fw_shipped']:,.0f} headsets** over three and a half months, and
**{S['bad_fw_faults']:,.0f}** had to be replaced. During Feb and Mar, members waited about two weeks for a working headset.

**What to do**
- **Staged rollout:** ship new firmware to about 5% of new headsets first; release widely only after 2 clean weeks.
- **Fault alert:** flag any firmware with more than 5% faults in its first 30 days (this dashboard can drive it).
- **Replacement buffer:** keep a small stock of spare headsets so a replacement ships within 2 days, even in a bad month.

With an alert at 5%, the 4.2.0 problem would likely have been caught within weeks, not months.
""")

    st.subheader("5. Trustworthy engagement status")
    st.markdown(f"""
**What the data says.** Headsets without home wifi upload sessions days later. About **{S['false_alarms_per_month']:.0f} times a month**,
an active member without wifi shows up as inactive, and **{S['active_no_wifi']:,.0f}** of today's {S['active_now']:,.0f} active members have no
home wifi.

**What to do:** base status on the headset's last sync time, give offline members a longer grace window, and offer a hotspot or
weekly sync reminder at intake.
""")

# ---------------------------------------------------------------- bundles
with tab3:
    st.subheader("6. Care bundles with partners")
    st.markdown(f"""
Members should keep using the headset as long as it helps. The way to grow value per member is to **pair VR with the care that
fits the condition**, and to make the headset part of a fuller program for each health plan.
""")
    seg = pd.DataFrame({
        "segment": ["Pain members with anxiety", "Anxiety track members", "Back, neck and joint pain"],
        "members": [S["pain_with_anxiety"], S["anxiety_track"], S["back_joint"]],
    })
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Members who started, by bundle target group**")
        fig = c.bar(seg, "segment", "members", horizontal=True, text_fmt="{:,.0f}", height=220,
                    color=[c.SERIES[0], c.SERIES[0], c.SERIES[2]])
        c.show(fig, key="rec_seg")
    with right:
        st.markdown("**Share of sessions spent on mindfulness and anxiety modules** (pain members)")
        mh = pd.DataFrame({"group": ["With anxiety", "Without anxiety"],
                           "share": [S["mh_share_comorbid"], S["mh_share_other"]]})
        fig = c.bar(mh, "group", "share", pct=True, text_fmt="{:.0%}", height=220, color=[c.SERIES[0], c.NEUTRAL])
        c.show(fig, key="rec_mh")

    b1, b2, b3 = st.columns(3)
    with b1:
        with st.container(border=True):
            st.markdown("**VR + online therapy**")
            st.markdown(f"For pain members with anxiety and the anxiety track. Pain members with anxiety already spend "
                        f"**{S['mh_share_comorbid']:.0%}** of sessions on mental health modules, about twice the rate of other pain "
                        f"members. Partner with a teletherapy provider for a warm handoff when a coach sees a member needs more.")
    with b2:
        with st.container(border=True):
            st.markdown("**VR + movement care**")
            st.markdown(f"For the **{S['back_joint']:,.0f}** back, neck and joint pain members, the largest group. Pair VR "
                        "(pain education, relaxation) with a digital physical therapy program or a TENS device, so members get "
                        "both the mind and body parts of pain care.")
    with b3:
        with st.container(border=True):
            st.markdown("**Maintenance after the program**")
            st.markdown(f"**{S['completers_keeping']:,.0f}** members kept their headset after completing, and "
                        f"**{S['completers_active']:,.0f}** still use it. Offer a lighter maintenance plan with a 90-day clinical "
                        "review, so members keep the headset while it helps and return it when it no longer does.")
    st.caption("Bundles are a hypothesis: the data shows the need, not the outcome. Run a pilot before scaling (see How we'll measure).")

# ---------------------------------------------------------------- measurement
with tab4:
    st.subheader("How we'll know it worked")
    plan = pd.DataFrame([
        ("First-week program", "A/B test: half of new members get day-2 and day-3 nudges", "3+ week-one sessions; day-30 retention", "6 to 8 weeks"),
        ("Idle headset policy", "Before vs after, by month", "Zero-use share of billing; headsets redeployed", "2 months"),
        ("Device guardrails", "Track each firmware's 30-day fault rate", "Fault rate; days without a working headset", "Ongoing"),
        ("Engagement status fix", "Re-run the status backtest monthly", "False 'inactive' rate for members without wifi", "1 month"),
        ("48-hour welcome call", "Weekly SLA report", "Share of welcome calls within 48 hours; activation", "Ongoing"),
        ("Care bundles", "90-day pilot with one plan vs matched members", "Day-90 retention, completion, pain scores, ER visits", "3 to 4 months"),
    ], columns=["Initiative", "Design", "Success metric", "Time to read"])
    st.dataframe(plan, hide_index=True, width="stretch")
    st.markdown("All metrics already exist in this app, so every initiative can be tracked from day one with the same definitions.")
