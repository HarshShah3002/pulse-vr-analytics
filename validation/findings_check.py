"""Run the headline business questions against the marts (what Omni dashboards will show)."""
from pathlib import Path
import duckdb

con = duckdb.connect(str(Path(__file__).resolve().parents[1] / "warehouse" / "pulse.duckdb"), read_only=True)


def q(title, sql):
    print("\n== " + title)
    print(con.execute(sql).df().to_string(index=False))


q("Funnel (delivered members with matured activation window)", """
select count(*) filter (where is_delivered) delivered,
       count(*) filter (where first_session_date is not null) started,
       count(*) filter (where is_activated) activated_14d,
       count(*) filter (where hit_week1_habit) week1_habit,
       count(*) filter (where retained_day30 and is_day30_matured) retained_d30,
       count(*) filter (where completed_program) completed
from marts.dim_members where is_delivered and is_activation_matured""")

q("Activation and D30 by 48h welcome reach (naive)", """
select welcome_reached_48h, count(*) n,
       round(avg(is_activated::int),3) activation,
       round(avg(retained_day30::int) filter (where is_day30_matured and first_session_date is not null),3) d30_of_starters
from marts.dim_members where is_delivered and is_activation_matured group by 1""")

q("Natural experiment: 48h attempt rate and activation by delivery month", """
select delivery_cohort_month, count(*) n,
       round(avg(welcome_attempted_48h::int),2) attempted48,
       round(avg(welcome_reached_48h::int),2) reached48,
       round(avg(is_activated::int),3) activation
from marts.dim_members where is_delivered and is_activation_matured group by 1 order by 1""")

q("Cohort heatmap sample (weekly retention % by delivery cohort)", """
select delivery_cohort_month,
  round(100*avg(is_active_week::int) filter (where program_week=1)) w1,
  round(100*avg(is_active_week::int) filter (where program_week=2)) w2,
  round(100*avg(is_active_week::int) filter (where program_week=4)) w4,
  round(100*avg(is_active_week::int) filter (where program_week=8)) w8,
  round(100*avg(is_active_week::int) filter (where program_week=12)) w12,
  round(100*avg(is_active_week::int) filter (where program_week=24)) w24
from marts.fct_member_weeks group by 1 order by 1""")

q("Engagement status mix (today)", """
select engagement_status, count(*) n from marts.dim_members group by 1 order by 2 desc""")

q("Status backtest: actually-active members the CRM showed as not active, by wifi", """
select has_home_wifi, count(*) filter (where status_actual = 'Active') actually_active,
       count(*) filter (where is_false_alarm) shown_inactive,
       round(count(*) filter (where is_false_alarm) / count(*) filter (where status_actual = 'Active'), 3) false_alarm_rate
from marts.fct_status_backtest group by 1""")

q("Zombie rental months", """
select count(*) billed_months, count(*) filter (where is_zombie_month) zombie_months,
       round(avg(is_zombie_month::int),3) zombie_share,
       sum(billed_amount_usd) filter (where is_zombie_month) zombie_billed_usd
from marts.fct_rental_months""")

q("Headsets at home right now with no session in 30+ days", """
select count(*) filter (where headset_at_home) at_home,
       count(*) filter (where headset_at_home and (days_since_last_session > 30 or first_session_date is null)) idle_30plus
from marts.dim_members""")

q("Device faults by firmware: retention impact", """
select initial_firmware_version, count(*) n, round(avg((replacement_count>0)::int),3) fault_rate,
       round(avg(retained_day30::int) filter (where is_day30_matured),3) d30
from marts.dim_members where first_session_date is not null group by 1 order by 1""")

q("Denials by plan", """
select payer_plan, count(*) n_months, round(avg(is_lost_revenue::int) filter (where invoice_status not in ('Pending','Submitted')),3) loss_rate
from marts.fct_rental_months group by 1 order by 3 desc""")

q("Pain outcomes by completion", """
select completed_program, count(*) n, round(avg(baseline_pain),2) base, round(avg(week7_8_pain),2) wk8,
       round(avg(pain_reduction_points),2) reduction
from marts.dim_members where baseline_pain is not null and week7_8_pain is not null group by 1""")

q("Comorbid pain + anxiety module mix", """
select m.has_comorbid_anxiety, round(avg((s.module in ('Mindfulness','Anxiety and Stress CBT'))::int),3) mind_anx_share
from marts.fct_sessions s join marts.dim_members m using (member_id)
where m.primary_condition <> 'Anxiety and stress' group by 1""")
