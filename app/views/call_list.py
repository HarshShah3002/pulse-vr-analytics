import streamlit as st

from lib import charts as c
from lib import metrics

c.page_header("Care team call list", "Who should coaches call this week, why, and what should they say?")

card = metrics.get("model_card").set_index("metric")["value"]
risk = metrics.get("risk")

c.insight(f"Members flagged <b>High</b> risk stopped within 30 days <b>{float(card['lapse_rate_high']):.0%}</b> of the time, "
          f"vs {float(card['lapse_rate_low']):.0%} for Low. Calling the riskiest 20% reaches "
          f"<b>{float(card['top20_capture']):.0%}</b> of members who are about to drop off.")

k = st.columns(4)
k[0].metric("Engaged members scored", f"{len(risk):,}", border=True)
k[1].metric("High risk", f"{(risk.risk_tier == 'High').sum():,}", border=True)
k[2].metric("Medium risk", f"{(risk.risk_tier == 'Medium').sum():,}", border=True)
k[3].metric("Model accuracy (AUC)", f"{float(card['auc_logistic']):.2f}", border=True,
            help="0.5 is a coin flip, 1.0 is perfect. Measured on Jul to Sep 2026, months the model never saw.")

f1, f2, f3 = st.columns(3)
coach = f1.selectbox("Coach", ["All coaches"] + sorted(risk.coach_name.dropna().unique()))
tiers = f2.multiselect("Risk tier", ["High", "Medium", "Low"], default=["High"])
plan = f3.selectbox("Health plan", ["All plans"] + sorted(risk.plan_name.unique()))

view = risk[risk.risk_tier.isin(tiers or ["High", "Medium", "Low"])]
if coach != "All coaches":
    view = view[view.coach_name == coach]
if plan != "All plans":
    view = view[view.plan_name == plan]
view = view.assign(phone=view.phone.fillna("No phone on file"), member=view.first_name + " " + view.last_name,
                   why=view.reason_1 + view.reason_2.fillna("").map(lambda r: f"; {r}" if r else ""))

st.dataframe(
    view[["member", "phone", "coach_name", "risk_tier", "risk_score", "why", "recommended_action",
          "days_since_last_session", "sessions_last_28d", "plan_name"]],
    hide_index=True, width="stretch", height=460,
    column_config={
        "member": "Member", "phone": "Phone", "coach_name": "Coach", "risk_tier": "Tier",
        "risk_score": st.column_config.ProgressColumn("Chance of stopping", format="percent", min_value=0, max_value=1),
        "why": st.column_config.TextColumn("Why flagged", width="large"),
        "recommended_action": st.column_config.TextColumn("Suggested next step", width="medium"),
        "days_since_last_session": st.column_config.NumberColumn("Days since last session", format="%d"),
        "sessions_last_28d": st.column_config.NumberColumn("Sessions, last 4 weeks", format="%d"),
        "plan_name": "Plan",
    },
)
st.download_button("Download this list (CSV)", view.drop(columns=["email"]).to_csv(index=False).encode(),
                   file_name="pulse_call_list.csv", mime="text/csv")
st.caption("Names and phone numbers are fictional. Scored as of Oct 31, 2026 for members with a session in the last 21 days "
           "and a headset at home.")

with st.expander("How the risk model works"):
    st.markdown(f"""
- **Predicts:** {card['target']}.
- **Learned from:** {card['train_snapshots']}; **tested on:** {card['validation_snapshots']}.
- **Signals it uses:** days since last session, recent vs earlier usage, session length and completion, first-week sessions,
  time in program, early coach contact, device swaps, recent coach conversations, home wifi, age, tech comfort, plan, track.
- **Why logistic regression:** gradient boosting scored {float(card['auc_gradient_boosting']):.3f} AUC vs
  {float(card['auc_logistic']):.3f}. That small gain isn't worth losing the plain-English reason a coach can say on the call.
- **Tiers:** High is the riskiest 20% (score ≥ {float(card['high_cutoff']):.0%}), Medium the next 30%, Low the rest.
- **Retrained:** weekly in production; here it is scored once on the snapshot.
""")
    c.show_sql("-- written by analytics/run_models.py\n" + metrics.SQL["risk"])
