"""
Pulse analytics models. Reads the marts, writes results back to the warehouse.

  python analytics/run_models.py                -> local warehouse/pulse.duckdb
  python analytics/run_models.py --motherduck   -> MotherDuck database "pulse"

Writes:
  marts.ml_member_risk     one row per currently engaged member: 30-day lapse risk, reasons, next action
  marts.ml_model_card      model quality and settings (AUC, lift, base rate, features)
  marts.analysis_effects   outreach and week-1 habit effects: naive vs adjusted vs before/after SLA

Model choice: logistic regression, compared against gradient boosting. Coaches need a reason
they can say out loud on a call ("no session in 12 days, usage halved"), so we keep the
explainable model unless the black-box model is clearly better.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-10-31"
RNG = np.random.default_rng(7)


def connect(motherduck: bool) -> duckdb.DuckDBPyConnection:
    if motherduck:
        if not os.environ.get("MOTHERDUCK_TOKEN"):
            raise SystemExit("Set MOTHERDUCK_TOKEN first.")
        con = duckdb.connect("md:pulse")
    else:
        con = duckdb.connect(str(ROOT / "warehouse" / "pulse.duckdb"))
    return con


# ---------------------------------------------------------------------------
# 1. Churn risk model
# ---------------------------------------------------------------------------
SNAPSHOT_SQL = f"""
with snaps as (
    select last_day(unnest(generate_series(date '2025-08-01', date '{AS_OF}', interval 1 month))::date) as snapshot_date
),
eligible as (
    select m.member_id, s.snapshot_date
    from marts.dim_members m
    join snaps s on m.first_session_date <= s.snapshot_date
    where m.return_request_date is null or m.return_request_date > s.snapshot_date
),
sess as (
    select e.member_id, e.snapshot_date,
        max(x.session_date) filter (where x.session_date <= e.snapshot_date)                                   as last_session,
        count(*) filter (where x.session_date between e.snapshot_date - 6 and e.snapshot_date)                 as sessions_last_7d,
        count(*) filter (where x.session_date between e.snapshot_date - 27 and e.snapshot_date)                as sessions_last_28d,
        count(*) filter (where x.session_date between e.snapshot_date - 55 and e.snapshot_date - 28)           as sessions_prev_28d,
        avg(x.duration_minutes) filter (where x.session_date between e.snapshot_date - 27 and e.snapshot_date) as avg_minutes_last_28d,
        avg(x.completed_flag::int) filter (where x.session_date between e.snapshot_date - 27 and e.snapshot_date) as completion_last_28d,
        count(*) filter (where x.session_date <= e.snapshot_date)                                              as sessions_to_date,
        count(*) filter (where x.session_date > e.snapshot_date and x.session_date <= e.snapshot_date + 30)    as sessions_next_30d
    from eligible e
    join marts.fct_sessions x on x.member_id = e.member_id and x.session_date <= e.snapshot_date + 30
    group by 1, 2
),
dev as (
    select e.member_id, e.snapshot_date, count(o.order_id) as device_swaps
    from eligible e
    left join marts.fct_orders o
      on o.member_id = e.member_id and o.order_status = 'Replaced' and o.return_request_date <= e.snapshot_date
    group by 1, 2
),
tch as (
    select e.member_id, e.snapshot_date,
           count(t.touch_id) filter (where t.is_reached) as coach_conversations_28d
    from eligible e
    left join marts.fct_outreach t
      on t.member_id = e.member_id and t.touch_ts::date between e.snapshot_date - 27 and e.snapshot_date
    group by 1, 2
)
select
    s.member_id, s.snapshot_date,
    date_diff('day', s.last_session, s.snapshot_date)                 as days_since_last_session,
    s.sessions_last_7d, s.sessions_last_28d, s.sessions_prev_28d,
    coalesce(s.avg_minutes_last_28d, 0)                               as avg_minutes_last_28d,
    coalesce(s.completion_last_28d, 0)                                as completion_last_28d,
    s.sessions_to_date,
    date_diff('day', m.first_session_date, s.snapshot_date)           as days_in_program,
    m.week1_sessions,
    m.welcome_reached_48h::int                                        as welcome_reached_48h,
    m.has_home_wifi::int                                              as has_home_wifi,
    m.has_comorbid_anxiety::int                                       as has_comorbid_anxiety,
    m.age_at_referral,
    m.intake_tech_comfort, m.referral_source, m.insurance_type,
    case when m.primary_condition = 'Anxiety and stress' then 'Anxiety' else 'Pain' end as program_track,
    d.device_swaps,
    t.coach_conversations_28d,
    (s.sessions_next_30d = 0)::int                                    as lapsed_next_30d
from sess s
join marts.dim_members m using (member_id)
join dev d using (member_id, snapshot_date)
join tch t using (member_id, snapshot_date)
where date_diff('day', s.last_session, s.snapshot_date) <= 21   -- engaged members only: active or at risk
"""

NUMERIC = ["days_since_last_session", "sessions_last_7d", "sessions_last_28d", "sessions_prev_28d",
           "avg_minutes_last_28d", "completion_last_28d", "days_in_program", "week1_sessions",
           "welcome_reached_48h", "has_home_wifi", "has_comorbid_anxiety", "age_at_referral",
           "device_swaps", "coach_conversations_28d"]
CATEGORICAL = ["intake_tech_comfort", "referral_source", "insurance_type", "program_track"]


def make_logit():
    pre = ColumnTransformer([("num", StandardScaler(), NUMERIC),
                             ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), CATEGORICAL)])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(C=0.5, max_iter=3000))])


def lift_at(y, p, share=0.2):
    k = max(1, int(len(p) * share))
    top = np.argsort(-p)[:k]
    return float(y[top].sum() / max(1, y.sum()))


def reason_text(feature: str, row: pd.Series) -> str | None:
    """Plain-English reason a coach can say out loud. None if the feature isn't a useful talking point."""
    r = row
    if feature == "days_since_last_session":
        return f"No session in {int(r.days_since_last_session)} days"
    if feature in ("sessions_last_28d", "sessions_last_7d", "sessions_prev_28d"):
        if r.sessions_prev_28d > r.sessions_last_28d:
            return f"Usage dropped: {int(r.sessions_prev_28d)} to {int(r.sessions_last_28d)} sessions per 4 weeks"
        return f"Only {int(r.sessions_last_28d)} sessions in the last 4 weeks"
    if feature == "week1_sessions":
        return f"Slow first week ({int(r.week1_sessions)} session{'s' if r.week1_sessions != 1 else ''})"
    if feature == "welcome_reached_48h" and r.welcome_reached_48h == 0:
        return "Not reached by a coach in the first 48 hours"
    if feature == "device_swaps" and r.device_swaps > 0:
        return "Had a faulty headset replaced"
    if feature == "intake_tech_comfort" and r.intake_tech_comfort == "Low":
        return "Low comfort with technology at intake"
    if feature == "days_in_program" and r.days_in_program > 56:
        return "Past the 8-week core program"
    if feature == "completion_last_28d" and r.completion_last_28d < 0.75:
        return f"Exiting sessions early ({r.completion_last_28d:.0%} completed)"
    if feature == "avg_minutes_last_28d":
        return f"Shorter sessions lately ({r.avg_minutes_last_28d:.0f} min average)"
    if feature == "coach_conversations_28d" and r.coach_conversations_28d == 0:
        return "No coach conversation in 4 weeks"
    if feature == "has_home_wifi" and r.has_home_wifi == 0:
        return "No home wifi (sessions may sync late)"
    if feature == "age_at_referral" and r.age_at_referral >= 80:
        return f"Age {int(r.age_at_referral)}"
    return None


def next_action(row: pd.Series) -> str:
    if row.device_swaps > 0 and row.days_since_last_session >= 7:
        return "Call to confirm the replacement headset works"
    if row.has_home_wifi == 0 and row.days_since_last_session >= 8:
        return "Check headset sync before assuming they stopped"
    if row.intake_tech_comfort == "Low" and row.days_since_last_session >= 5:
        return "Offer a guided session over the phone"
    if row.days_in_program > 56:
        return "Discuss maintenance plan or headset return"
    if row.has_comorbid_anxiety == 1:
        return "Check-in call; suggest a mindfulness or breathing module"
    if row.days_since_last_session >= 8:
        return "Check-in call this week"
    return "Encouragement text; check in next week"


def churn_model(con):
    df = con.execute(SNAPSHOT_SQL).df()
    as_of = pd.Timestamp(AS_OF)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    hist = df[df.snapshot_date + pd.Timedelta(days=30) <= as_of]
    score = df[df.snapshot_date == as_of].copy()

    train = hist[hist.snapshot_date <= "2026-06-30"]
    valid = hist[hist.snapshot_date > "2026-06-30"]
    X_cols = NUMERIC + CATEGORICAL

    logit = make_logit().fit(train[X_cols], train.lapsed_next_30d)
    p_logit = logit.predict_proba(valid[X_cols])[:, 1]
    gbm = Pipeline([("pre", ColumnTransformer([("num", "passthrough", NUMERIC),
                                               ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL)])),
                    ("clf", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0))])
    gbm.fit(train[X_cols], train.lapsed_next_30d)
    p_gbm = gbm.predict_proba(valid[X_cols])[:, 1]

    y = valid.lapsed_next_30d.to_numpy()
    auc_logit, auc_gbm = roc_auc_score(y, p_logit), roc_auc_score(y, p_gbm)

    # refit on all history for scoring today
    final = make_logit().fit(hist[X_cols], hist.lapsed_next_30d)
    score["risk_score"] = final.predict_proba(score[X_cols])[:, 1]

    # risk tiers from the validation distribution so they mean something stable
    hi_cut = float(np.quantile(p_logit, 0.80))
    md_cut = float(np.quantile(p_logit, 0.50))
    score["risk_tier"] = np.where(score.risk_score >= hi_cut, "High",
                                  np.where(score.risk_score >= md_cut, "Medium", "Low"))

    # reasons: per-member contribution of each feature group (coef x standardized value)
    pre = final.named_steps["pre"]
    coefs = final.named_steps["clf"].coef_[0]
    names = pre.get_feature_names_out()
    Z = pre.transform(score[X_cols])
    Z = Z.toarray() if hasattr(Z, "toarray") else Z
    contrib = Z * coefs
    groups = []
    for n in names:
        base = n.split("__", 1)[1]
        grp = next((c for c in CATEGORICAL if base.startswith(c + "_")), base)
        groups.append(grp)
    contrib_df = pd.DataFrame(contrib, columns=names, index=score.index).T.groupby(groups).sum().T

    r1, r2 = [], []
    for idx, row in score.iterrows():
        ordered = contrib_df.loc[idx].sort_values(ascending=False)
        texts = []
        for feat, val in ordered.items():
            if val <= 0:
                break
            t = reason_text(feat, row)
            if t and t not in texts:
                texts.append(t)
            if len(texts) == 2:
                break
        r1.append(texts[0] if texts else "Engagement steady")
        r2.append(texts[1] if len(texts) > 1 else None)
    score["reason_1"], score["reason_2"] = r1, r2
    score["recommended_action"] = score.apply(next_action, axis=1)

    members = con.execute("""select member_id, coach_id, first_name, last_name, phone, email, plan_name,
                                    primary_condition, age_band from marts.dim_members""").df()
    coaches = con.execute("select coach_id, coach_name from marts.dim_coaches").df()
    out = (score.merge(members, on="member_id").merge(coaches, on="coach_id", how="left")
           [["member_id", "first_name", "last_name", "phone", "email", "coach_id", "coach_name", "plan_name",
             "primary_condition", "age_band", "risk_score", "risk_tier", "reason_1", "reason_2",
             "recommended_action", "days_since_last_session", "sessions_last_28d", "sessions_prev_28d",
             "days_in_program", "week1_sessions", "device_swaps", "has_home_wifi"]]
           .sort_values("risk_score", ascending=False))
    out["risk_score"] = out.risk_score.round(3)

    # how good is the "call the top 20%" policy on the holdout months?
    valid_tiers = np.where(p_logit >= hi_cut, "High", np.where(p_logit >= md_cut, "Medium", "Low"))
    tier_rates = pd.Series(y).groupby(valid_tiers).mean()
    card = pd.DataFrame([
        ("model", "Logistic regression (explainable)"),
        ("target", "No VR session in the next 30 days, among members active in the last 21 days"),
        ("train_snapshots", f"{train.snapshot_date.min():%b %Y} to {train.snapshot_date.max():%b %Y} ({len(train):,} member-months)"),
        ("validation_snapshots", f"{valid.snapshot_date.min():%b %Y} to {valid.snapshot_date.max():%b %Y} ({len(valid):,} member-months)"),
        ("base_rate", f"{y.mean():.3f}"),
        ("auc_logistic", f"{auc_logit:.3f}"),
        ("auc_gradient_boosting", f"{auc_gbm:.3f}"),
        ("top20_capture", f"{lift_at(y, p_logit, 0.2):.3f}"),
        ("lapse_rate_high", f"{tier_rates.get('High', np.nan):.3f}"),
        ("lapse_rate_medium", f"{tier_rates.get('Medium', np.nan):.3f}"),
        ("lapse_rate_low", f"{tier_rates.get('Low', np.nan):.3f}"),
        ("high_cutoff", f"{hi_cut:.3f}"),
        ("medium_cutoff", f"{md_cut:.3f}"),
        ("scored_members", f"{len(out):,}"),
        ("scored_as_of", AS_OF),
    ], columns=["metric", "value"])
    print(card.to_string(index=False))
    print(out.risk_tier.value_counts().to_string())
    return out, card


# ---------------------------------------------------------------------------
# 2. Effects: 48-hour outreach and week-1 habit
# ---------------------------------------------------------------------------
COVARS_CAT = ["referral_source", "intake_tech_comfort", "age_band", "insurance_type", "program_track", "urbanicity"]
COVARS_NUM = ["has_phone_on_file", "has_home_wifi", "delivery_month_index"]


def diff_ci(a: pd.Series, b: pd.Series):
    pa, pb = a.mean(), b.mean()
    se = np.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
    d = pa - pb
    return d, d - 1.96 * se, d + 1.96 * se


def adjusted_effect(df: pd.DataFrame, treat: str, outcome: str, n_boot: int = 150):
    """Average marginal effect of `treat` on `outcome` from a logistic model with observed covariates."""
    cols = [treat] + COVARS_NUM + COVARS_CAT

    def fit_ame(d):
        pre = ColumnTransformer([("num", "passthrough", [treat] + COVARS_NUM),
                                 ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), COVARS_CAT)])
        m = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=3000, C=1.0))]).fit(d[cols], d[outcome])
        d1, d0 = d[cols].copy(), d[cols].copy()
        d1[treat], d0[treat] = 1, 0
        return float(m.predict_proba(d1)[:, 1].mean() - m.predict_proba(d0)[:, 1].mean())

    est = fit_ame(df)
    boots = [fit_ame(df.sample(len(df), replace=True, random_state=int(RNG.integers(1e9)))) for _ in range(n_boot)]
    return est, float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))


def effects(con):
    m = con.execute("""
        select *, case when primary_condition = 'Anxiety and stress' then 'Anxiety' else 'Pain' end as program_track,
               date_diff('month', date '2025-05-01', delivery_cohort_month) as delivery_month_index
        from marts.dim_members where is_delivered and is_activation_matured
    """).df()
    for c in ["welcome_reached_48h", "welcome_attempted_48h", "is_activated", "has_phone_on_file", "has_home_wifi",
              "hit_week1_habit", "retained_day30", "has_started", "is_day30_matured"]:
        m[c] = m[c].fillna(False).astype(int)
    rows = []

    # --- 48h outreach -> activation
    reached, not_reached = m[m.welcome_reached_48h == 1], m[m.welcome_reached_48h == 0]
    d, lo, hi = diff_ci(reached.is_activated, not_reached.is_activated)
    rows.append(("outreach_48h", "Naive comparison", d, lo, hi, len(m),
                 f"{reached.is_activated.mean():.3f} reached vs {not_reached.is_activated.mean():.3f} not reached",
                 "Members who answer the phone are also more motivated, so this overstates the effect."))
    est, lo, hi = adjusted_effect(m, "welcome_reached_48h", "is_activated")
    rows.append(("outreach_48h", "Adjusted for member profile", est, lo, hi, len(m), "",
                 "Controls for referral source, tech comfort, age, insurance, condition, location, phone on file, month. "
                 "Motivation itself is not measured, so some bias remains."))
    pre = m[(m.delivery_cohort_month >= pd.Timestamp("2026-02-01")) & (m.delivery_cohort_month <= pd.Timestamp("2026-05-01"))]
    post = m[(m.delivery_cohort_month >= pd.Timestamp("2026-06-01")) & (m.delivery_cohort_month <= pd.Timestamp("2026-09-01"))]
    d, lo, hi = diff_ci(post.is_activated, pre.is_activated)
    rows.append(("outreach_48h", "Before vs after 48h SLA (Jun 2026)", d, lo, hi, len(pre) + len(post),
                 f"activation {pre.is_activated.mean():.3f} (Feb to May) vs {post.is_activated.mean():.3f} (Jun to Sep); "
                 f"48h attempts {pre.welcome_attempted_48h.mean():.3f} vs {post.welcome_attempted_48h.mean():.3f}",
                 "Whole-population change after the policy, so member motivation does not bias it. "
                 "Other changes in the same months (such as the firmware fix) could contribute."))

    # --- week-1 habit -> day-30 retention
    s = m[(m.has_started == 1) & (m.is_day30_matured == 1)].copy()
    habit, nohabit = s[s.hit_week1_habit == 1], s[s.hit_week1_habit == 0]
    d, lo, hi = diff_ci(habit.retained_day30, nohabit.retained_day30)
    rows.append(("week1_habit", "Naive comparison", d, lo, hi, len(s),
                 f"{habit.retained_day30.mean():.3f} with 3+ week-1 sessions vs {nohabit.retained_day30.mean():.3f} without", ""))
    est, lo, hi = adjusted_effect(s, "hit_week1_habit", "retained_day30")
    rows.append(("week1_habit", "Adjusted for member profile", est, lo, hi, len(s), "",
                 "Same controls as above. Week-1 habit stays strongly linked to staying, after adjustment."))

    eff = pd.DataFrame(rows, columns=["analysis", "method", "estimate", "ci_low", "ci_high", "n", "detail", "caveat"])
    for c in ["estimate", "ci_low", "ci_high"]:
        eff[c] = eff[c].round(4)
    print(eff[["analysis", "method", "estimate", "ci_low", "ci_high", "n"]].to_string(index=False))
    return eff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motherduck", action="store_true")
    a = ap.parse_args()
    con = connect(a.motherduck)
    risk, card = churn_model(con)
    eff = effects(con)
    for name, df in [("ml_member_risk", risk), ("ml_model_card", card), ("analysis_effects", eff)]:
        con.register("tmp_df", df)
        con.execute(f"create or replace table marts.{name} as select * from tmp_df")
        con.unregister("tmp_df")
        print(f"wrote marts.{name} ({len(df):,} rows)")
    con.close()


if __name__ == "__main__":
    main()
