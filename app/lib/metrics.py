"""
Metrics layer: every number in the app comes from a named query here, so definitions live in one place
(the same idea as a semantic layer in a BI tool). Pages call `get(name)`.
"""
from __future__ import annotations

import pandas as pd

from lib.db import run

DEFINITIONS = {
    "Activated": "First VR session within 14 days of headset delivery. Only members delivered 14+ days before the snapshot count.",
    "Week-1 habit": "3 or more sessions in the 7 days starting with the member's first session.",
    "Day-30 retention": "Of members who started, share with at least one session in days 28 to 34 after their first session. Only members whose window has passed count.",
    "Engagement status": "From the real session date on the headset: Active (session in last 7 days), At risk (8 to 21), Lapsed (22 to 45), Churned (over 45 days or headset returned), plus Never activated, Completed, Not enrolled, Awaiting delivery.",
    "Reached within 48 hours": "A coach spoke with the member within 48 hours of delivery (60-hour tolerance for weekends).",
    "Completed program": "28+ sessions spanning 8+ weeks, or headset returned after completing.",
    "Zero-use rental month": "A billed monthly rental (HCPCS E1905) in which the member did no sessions.",
    "Idle headset": "Still at the member's home, delivered 30+ days ago, no session in 30+ days.",
    "CRM false alarm": "Member was truly active at month end, but the CRM (which only sees synced sessions) showed them as not active.",
    "Lapse risk": "Model-estimated chance an engaged member does no session in the next 30 days.",
}

SEGMENTS = {
    "Referral source": "referral_source",
    "Tech comfort at intake": "intake_tech_comfort",
    "Age band": "age_band",
    "Insurance type": "insurance_type",
    "Health plan": "plan_name",
    "Program track": "primary_condition",
    "Urban or rural": "urbanicity",
    "Home wifi": "case when has_home_wifi then 'Has wifi' else 'No wifi' end",
    "Reached in 48 hours": "case when welcome_reached_48h then 'Reached in 48h' else 'Not reached in 48h' end",
    "Week-1 sessions": "week1_bucket",
    "Headset firmware": "initial_firmware_version",
}
# fct_member_weeks carries a subset of member attributes
CURVE_SEGMENTS = ["Week-1 sessions", "Reached in 48 hours", "Program track", "Insurance type", "Health plan",
                  "Age band", "Referral source", "Home wifi", "Headset firmware"]

SQL = {
    # ---------------- overview ----------------
    "kpi": """
with m as (select * from marts.dim_members)
select
  (select count(*) from m where engagement_status = 'Active')                                            as active_now,
  (select count(*) from marts.fct_status_backtest where snapshot_date = date '2026-09-30' and status_actual = 'Active') as active_prev,
  (select avg(is_activated::int) from m where is_delivered and is_activation_matured
       and delivery_cohort_month between date '2026-07-01' and date '2026-09-01')                         as activation_recent,
  (select avg(is_activated::int) from m where is_delivered and is_activation_matured
       and delivery_cohort_month between date '2026-04-01' and date '2026-06-01')                         as activation_prior,
  (select avg(retained_day30::int) from m where has_started and is_day30_matured
       and first_session_date between date '2026-07-01' and date '2026-09-30')                            as d30_recent,
  (select avg(retained_day30::int) from m where has_started and is_day30_matured
       and first_session_date between date '2026-04-01' and date '2026-06-30')                            as d30_prior,
  (select avg(completed_program::int) from m where has_started and is_day60_matured)                     as completion_rate,
  (select count(*) from m where is_idle_headset_30d)                                                      as idle_headsets,
  (select sum(billed_amount_usd) filter (where is_zombie_month) from marts.fct_rental_months
       where service_period_start > date '2026-08-02')                                                     as zero_use_billed_90d,
  (select sum(billed_amount_usd) from marts.fct_rental_months where service_period_start > date '2026-08-02') as billed_90d,
  (select count(*) from marts.ml_member_risk where risk_tier = 'High')                                    as high_risk
""",
    "monthly": """
select delivery_cohort_month as month,
       count(*)                                                               as delivered,
       avg(is_activated::int) filter (where is_activation_matured)            as activation_rate,
       avg(welcome_attempted_48h::int)                                        as attempted_48h_rate,
       avg(welcome_reached_48h::int)                                          as reached_48h_rate,
       median(days_to_first_session)                                          as median_days_to_start
from marts.dim_members
where is_delivered
group by 1 order by 1
""",
    "weekly_active": """
select date_trunc('week', session_date)::date as week, count(distinct member_id) as active_members,
       count(*) as sessions
from marts.fct_sessions
where date_trunc('week', session_date)::date + 6 <= date '2026-10-31'
group by 1 order by 1
""",
    "status_mix": """
select engagement_status as status, count(*) as members
from marts.dim_members
where engagement_status not in ('Not enrolled', 'Awaiting delivery')
group by 1
""",
    # ---------------- activation ----------------
    "funnel": """
with m as (select * from marts.dim_members where referral_date <= date '2026-06-30')
select * from (values
  (1, 'Referred',                      (select count(*) from m)),
  (2, 'Enrolled (insurance verified)', (select count(*) from m where onboarding_date is not null)),
  (3, 'Headset delivered',             (select count(*) from m where is_delivered)),
  (4, 'Started (any session)',         (select count(*) from m where has_started)),
  (5, 'Activated within 14 days',      (select count(*) from m where is_activated)),
  (6, '3+ sessions in week 1',         (select count(*) from m where hit_week1_habit)),
  (7, 'Still active at day 30',        (select count(*) from m where retained_day30)),
  (8, 'Completed 8-week program',      (select count(*) from m where completed_program))
) t(step, stage, members)
order by step
""",
    "days_to_start": """
select case when days_to_first_session is null then 'Never'
            when days_to_first_session >= 15 then '15+'
            else days_to_first_session::varchar end as days,
       coalesce(days_to_first_session, 99) as sort_key,
       count(*) as members
from marts.dim_members
where is_delivered and is_activation_matured
group by 1, 2 order by 2
""",
    # ---------------- retention ----------------
    "cohort_heatmap": """
select first_session_cohort_month as cohort, program_week as week,
       avg(is_active_week::int) as retention, count(*) as members
from marts.fct_member_weeks
where is_cohort_cell_complete and program_week <= 12
group by 1, 2 order by 1, 2
""",
    "d30_by_week1": """
select week1_bucket as bucket,
       case week1_bucket when '1 session' then 1 when '2 sessions' then 2 when '3 to 4 sessions' then 3 else 4 end as sort_key,
       count(*) as members, avg(retained_day30::int) as d30, avg(retained_day90::int) filter (where is_day90_matured) as d90
from marts.dim_members
where has_started and is_day30_matured
group by 1, 2 order by 2
""",
    "d30_by_week1_minutes": """
select case when week1_avg_minutes < 6 then 'Under 6 min' when week1_avg_minutes < 8 then '6 to 8 min'
            when week1_avg_minutes < 10 then '8 to 10 min' else '10+ min' end as bucket,
       case when week1_avg_minutes < 6 then 1 when week1_avg_minutes < 8 then 2 when week1_avg_minutes < 10 then 3 else 4 end as sort_key,
       count(*) as members, avg(retained_day30::int) as d30
from marts.dim_members
where has_started and is_day30_matured
group by 1, 2 order by 2
""",
    "effects": "select * from marts.analysis_effects",
    # ---------------- engagement ----------------
    "recency": """
select case when days_since_last_session <= 7 then '0 to 7' when days_since_last_session <= 14 then '8 to 14'
            when days_since_last_session <= 21 then '15 to 21' when days_since_last_session <= 30 then '22 to 30'
            when days_since_last_session <= 45 then '31 to 45' when days_since_last_session <= 90 then '46 to 90'
            else '90+' end as bucket,
       min(days_since_last_session) as sort_key, count(*) as members
from marts.dim_members
where headset_at_home and has_started
group by 1 order by 2
""",
    "modules": """
select module, count(*) as sessions, median(duration_minutes) as median_minutes,
       avg(completed_flag::int) as completion_rate, avg(in_session_pain_relief) as avg_pain_relief,
       count(distinct member_id) as members
from marts.fct_sessions
group by 1 order by sessions desc
""",
    "time_of_day": """
select time_of_day, count(*) as sessions,
       case time_of_day when 'Morning' then 1 when 'Afternoon' then 2 else 3 end as sort_key
from marts.fct_sessions group by 1, 3 order by 3
""",
    "duration_hist": """
select least(floor(duration_minutes / 2) * 2, 20)::int as minutes_from, count(*) as sessions
from marts.fct_sessions group by 1 order by 1
""",
    "crm_accuracy": """
select case when has_home_wifi then 'Has home wifi' else 'No home wifi' end as wifi,
       count(*) filter (where status_actual = 'Active') as truly_active,
       count(*) filter (where is_false_alarm) as shown_not_active,
       count(*) filter (where is_false_alarm) / nullif(count(*) filter (where status_actual = 'Active'), 0) as false_alarm_rate
from marts.fct_status_backtest group by 1 order by 1
""",
    # ---------------- outreach ----------------
    "touch_mix": """
select touch_month as month, touch_type, count(*) as touches
from marts.fct_outreach
where touch_month <= date '2026-10-01'
group by 1, 2 order by 1
""",
    "reach_by_type": """
select touch_type, count(*) filter (where channel = 'Call') as calls,
       avg(is_reached::int) filter (where channel = 'Call') as call_reach_rate
from marts.fct_outreach group by 1 order by calls desc
""",
    # ---------------- devices and billing ----------------
    "fault_by_firmware": """
select firmware_version, count(*) filter (where delivery_date is not null) as shipped,
       count(*) filter (where order_status = 'Replaced') / nullif(count(*) filter (where delivery_date is not null), 0) as fault_rate,
       avg(days_without_working_device) as avg_days_without_device
from marts.fct_orders where headset_id is not null
group by 1 order by 1
""",
    "replacement_turnaround": """
select date_trunc('month', return_request_date)::date as month, count(*) as replacements,
       avg(days_without_working_device) as avg_days_without_device
from marts.fct_orders where order_status = 'Replaced'
group by 1 order by 1
""",
    "d30_by_firmware": """
select initial_firmware_version as firmware_version, count(*) as members, avg(retained_day30::int) as d30
from marts.dim_members where has_started and is_day30_matured group by 1 order by 1
""",
    "return_reasons": """
select return_reason, count(*) as headsets,
       case when return_reason in ('Program completed', 'Rental term ended') then 'Healthy exit'
            when return_reason in ('Insurance change', 'Deceased') then 'Outside our control'
            else 'Avoidable' end as category
from marts.fct_orders
where order_status in ('Returned', 'Return requested')
group by 1, 3 order by 2 desc
""",
    "billing_monthly": """
select service_month as month, count(*) as billed_months, sum(billed_amount_usd) as billed_usd,
       sum(paid_amount_usd) as paid_usd, avg(is_zombie_month::int) as zero_use_share,
       sum(billed_amount_usd) filter (where is_zombie_month) as zero_use_billed_usd
from marts.fct_rental_months
where service_month <= date '2026-10-01'
group by 1 order by 1
""",
    "denials_by_plan": """
select payer_plan as plan,
       count(*) filter (where invoice_status in ('Paid', 'Denied', 'Appealed', 'Written off')) as decided_claims,
       count(*) filter (where is_lost_revenue)
         / nullif(count(*) filter (where invoice_status in ('Paid', 'Denied', 'Appealed', 'Written off')), 0) as denial_rate
from marts.fct_rental_months group by 1 order by denial_rate desc
""",
    "idle_by_age": """
select case when first_session_date is null then 'Never used'
            when days_since_last_session <= 45 then '31 to 45 days idle'
            when days_since_last_session <= 90 then '46 to 90 days idle' else '90+ days idle' end as bucket,
       count(*) as headsets
from marts.dim_members where is_idle_headset_30d group by 1
""",
    # ---------------- call list ----------------
    "risk": "select * from marts.ml_member_risk",
    "model_card": "select * from marts.ml_model_card",
}


def get(name: str) -> pd.DataFrame:
    return run(SQL[name])


def by_segment(name: str, segment_label: str) -> tuple[pd.DataFrame, str]:
    """Segment breakdowns, built from a whitelisted segment expression."""
    seg = SEGMENTS[segment_label]
    if name == "activation":
        sql = f"""
select {seg} as segment, count(*) as members, avg(is_activated::int) as activation_rate
from marts.dim_members where is_delivered and is_activation_matured
group by 1 having count(*) >= 30 order by activation_rate desc"""
    elif name == "d30":
        sql = f"""
select {seg} as segment, count(*) as members, avg(retained_day30::int) as d30
from marts.dim_members where has_started and is_day30_matured
group by 1 having count(*) >= 30 order by d30 desc"""
    elif name == "curve":
        sql = f"""
select {seg} as segment, program_week as week, avg(is_active_week::int) as retention, count(*) as members
from marts.fct_member_weeks
where program_week <= 12
group by 1, 2 having count(*) >= 30 order by 1, 2"""
    else:
        raise KeyError(name)
    return run(sql), sql.strip()
