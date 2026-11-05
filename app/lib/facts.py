"""
The fact sheet: the only numbers the AI is allowed to use. Every fact is computed from the warehouse,
so the AI explains the data rather than inventing it, and the fact checker can verify each number.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import metrics


def _f(key, label, value, kind, display=None):
    if display is None:
        if value is None or pd.isna(value):
            display = "n/a"
        elif kind == "pct":
            display = f"{value:.0%}"
        elif kind == "pts":
            display = f"{value * 100:+.0f} points"
        elif kind == "usd":
            display = f"${value / 1000:,.0f}K" if abs(value) < 1_000_000 else f"${value / 1_000_000:.2f}M"
        elif kind == "count":
            display = f"{value:,.0f}"
        else:
            display = f"{value:,.1f}"
    return {"key": key, "label": label, "value": None if value is None or pd.isna(value) else float(value),
            "kind": kind, "display": display}


@st.cache_data(ttl=900, show_spinner=False)
def compute_facts() -> list[dict]:
    k = metrics.get("kpi").iloc[0]
    eff = metrics.get("effects").set_index(["analysis", "method"])
    w1 = metrics.get("d30_by_week1").set_index("bucket")
    w1m = metrics.get("d30_by_week1_minutes").set_index("bucket")
    fw = metrics.get("fault_by_firmware").set_index("firmware_version")
    crm = metrics.get("crm_accuracy").set_index("wifi")
    card = metrics.get("model_card").set_index("metric")["value"]
    rr = metrics.get("return_reasons")
    den = metrics.get("denials_by_plan")
    mods = metrics.get("modules")
    turn = metrics.get("replacement_turnaround")
    monthly = metrics.get("monthly")

    pre = monthly[(monthly.month >= pd.Timestamp("2026-02-01")) & (monthly.month <= pd.Timestamp("2026-05-01"))]
    post = monthly[(monthly.month >= pd.Timestamp("2026-06-01")) & (monthly.month <= pd.Timestamp("2026-09-01"))]
    slow = turn[(turn.month >= pd.Timestamp("2026-02-01")) & (turn.month <= pd.Timestamp("2026-03-01"))]
    normal = turn[~turn.month.isin(slow.month)]
    avoidable = rr[rr.category == "Avoidable"].headsets.sum() / rr.headsets.sum()
    other_fw = fw.drop(index="4.2.0")
    best_mod = mods.sort_values("completion_rate", ascending=False).iloc[0]
    relief_mod = mods.dropna(subset=["avg_pain_relief"]).sort_values("avg_pain_relief", ascending=False).iloc[0]

    facts = [
        _f("active_now", "Members active in the last 7 days (Oct 31 2026)", k.active_now, "count"),
        _f("active_prev", "Members active at Sep 30 2026", k.active_prev, "count"),
        _f("activation_recent", "Activation rate, deliveries Jul to Sep 2026", k.activation_recent, "pct"),
        _f("activation_prior", "Activation rate, deliveries Apr to Jun 2026", k.activation_prior, "pct"),
        _f("d30_recent", "Day-30 retention, members starting Jul to Sep 2026", k.d30_recent, "pct"),
        _f("d30_prior", "Day-30 retention, members starting Apr to Jun 2026", k.d30_prior, "pct"),
        _f("completion_rate", "8-week program completion rate among members who started", k.completion_rate, "pct"),
        _f("idle_headsets", "Headsets at home with no session in 30+ days", k.idle_headsets, "count"),
        _f("zero_use_billed_90d", "Rental billed for months with zero use, last 90 days", k.zero_use_billed_90d, "usd"),
        _f("zero_use_share_90d", "Share of last-90-day rental billing with zero use", k.zero_use_billed_90d / k.billed_90d, "pct"),
        _f("high_risk", "Engaged members at high risk of lapsing in the next 30 days", k.high_risk, "count"),
        _f("model_top20_capture", "Share of upcoming lapses found by calling the riskiest 20%", float(card["top20_capture"]), "pct"),
        _f("lapse_rate_high", "30-day lapse rate for members flagged high risk", float(card["lapse_rate_high"]), "pct"),
        _f("lapse_rate_low", "30-day lapse rate for members flagged low risk", float(card["lapse_rate_low"]), "pct"),
        _f("d30_week1_one", "Day-30 retention with 1 session in week 1", w1.loc["1 session", "d30"], "pct"),
        _f("d30_week1_five", "Day-30 retention with 5+ sessions in week 1", w1.loc["5+ sessions", "d30"], "pct"),
        _f("habit_effect_adjusted", "Day-30 retention lift from a 3+ session first week (adjusted)",
           eff.loc[("week1_habit", "Adjusted for member profile"), "estimate"], "pts"),
        _f("d30_minutes_sweet", "Day-30 retention when week-1 sessions average 8 to 10 minutes", w1m.loc["8 to 10 min", "d30"], "pct"),
        _f("d30_minutes_short", "Day-30 retention when week-1 sessions average under 6 minutes", w1m.loc["Under 6 min", "d30"], "pct"),
        _f("d30_minutes_long", "Day-30 retention when week-1 sessions average 10+ minutes", w1m.loc["10+ min", "d30"], "pct"),
        _f("outreach_naive", "Activation gap, reached in 48h vs not (raw)",
           eff.loc[("outreach_48h", "Naive comparison"), "estimate"], "pts"),
        _f("outreach_sla", "Activation change after the 48-hour welcome call SLA (all new members)",
           eff.loc[("outreach_48h", "Before vs after 48h SLA (Jun 2026)"), "estimate"], "pts"),
        _f("attempt48_pre", "Welcome calls attempted within 48h, Feb to May 2026", pre.attempted_48h_rate.mean(), "pct"),
        _f("attempt48_post", "Welcome calls attempted within 48h, Jun to Sep 2026", post.attempted_48h_rate.mean(), "pct"),
        _f("fault_bad_fw", "Fault rate, firmware 4.2.0 (shipped Jan to Apr 2026)", fw.loc["4.2.0", "fault_rate"], "pct"),
        _f("fault_other_fw", "Fault rate, other firmware versions",
           (other_fw.fault_rate * other_fw.shipped).sum() / other_fw.shipped.sum(), "pct"),
        _f("downtime_slow", "Avg days without a working headset, Feb to Mar 2026 replacements",
           (slow.avg_days_without_device * slow.replacements).sum() / slow.replacements.sum(), "num"),
        _f("downtime_normal", "Avg days without a working headset, other months",
           (normal.avg_days_without_device * normal.replacements).sum() / normal.replacements.sum(), "num"),
        _f("crm_false_alarm_nowifi", "Truly active members without home wifi that the CRM showed as not active",
           crm.loc["No home wifi", "false_alarm_rate"], "pct"),
        _f("avoidable_return_share", "Share of returned headsets that were avoidable exits", avoidable, "pct"),
        _f("top_denial_plan_rate", f"Claim denial rate, {den.iloc[0].plan} (highest)", den.iloc[0].denial_rate, "pct"),
        _f("best_completion_module", f"Session completion rate, {best_mod.module} (highest)", best_mod.completion_rate, "pct"),
        _f("best_relief_module", f"Avg in-session pain relief (0 to 10 scale), {relief_mod.module} (highest)",
           relief_mod.avg_pain_relief, "num"),
    ]
    return facts


def facts_table(facts: list[dict]) -> str:
    return "\n".join(f"- {f['label']}: {f['display']}" for f in facts)


def fd(facts: list[dict]) -> dict:
    return {f["key"]: f for f in facts}
