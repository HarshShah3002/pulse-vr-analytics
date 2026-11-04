-- =====================================================================
-- MARTS: business-ready tables that Omni models sit on.
-- The as-of date is the data snapshot date (when the export was taken).
-- Metric definitions (used everywhere, including the Omni AI context):
--   Activated            first VR session within 14 days of headset delivery
--   Week-1 sessions      sessions in the 7 days starting with the first session
--   Retained (week N)    at least one session in days [7N, 7N+6] after the first session
--   Day-30 retained      retained in week 4 (days 28 to 34)
--   Engagement status    based on TRUE session time (device clock), not CRM sync time
--   Zombie rental month  a billed rental month with zero sessions in that service period
-- =====================================================================
create schema if not exists marts;

create or replace macro as_of() as date '2026-10-31';

-- ---------------------------------------------------------------------
-- fct_sessions: one row per real session (accidental launches removed)
-- ---------------------------------------------------------------------
create or replace table marts.fct_sessions as
with first_s as (
    select member_id, min(session_start_ts) as first_session_ts
    from staging.stg_sessions
    where not is_accidental_launch
    group by 1
)
select
    s.*,
    date_diff('day', f.first_session_ts::date, s.session_date)             as day_in_program,
    date_diff('day', f.first_session_ts::date, s.session_date) // 7        as program_week,
    hour(s.session_start_ts)                                               as hour_of_day,
    case when hour(s.session_start_ts) < 12 then 'Morning'
         when hour(s.session_start_ts) < 17 then 'Afternoon'
         else 'Evening' end                                                as time_of_day
from staging.stg_sessions s
join first_s f using (member_id)
where not s.is_accidental_launch;

-- ---------------------------------------------------------------------
-- dim_members: one row per member with their whole journey
-- ---------------------------------------------------------------------
create or replace table marts.dim_members as
with initial_order as (
    select * from staging.stg_orders where order_type = 'Initial'
),
current_order as (
    select * from (
        select *, row_number() over (partition by member_id order by order_id desc) rn
        from staging.stg_orders
    ) where rn = 1
),
faults as (
    select member_id, count(*) as replacement_count,
           avg(date_diff('day', return_request_date, replacement_date)) as avg_days_without_device
    from staging.stg_orders where order_status = 'Replaced' group by 1
),
sess as (
    select member_id,
           min(session_date) as first_session_date,
           max(session_date) as last_session_date,
           max(case when synced_at_ts::date <= as_of() then session_date end) as last_synced_session_date,
           count(*) as total_sessions,
           sum(duration_minutes) as total_minutes,
           avg(duration_minutes) as avg_session_minutes,
           count(*) filter (where day_in_program between 0 and 6) as week1_sessions,
           avg(duration_minutes) filter (where day_in_program between 0 and 6) as week1_avg_minutes,
           bool_or(day_in_program between 28 and 34) as active_week4,
           bool_or(day_in_program between 56 and 62) as active_week8,
           bool_or(day_in_program between 84 and 90) as active_week12,
           avg(pre_pain_score) filter (where day_in_program between 0 and 13) as baseline_pain,
           avg(pre_pain_score) filter (where day_in_program between 42 and 62) as week7_8_pain
    from marts.fct_sessions group by 1
),
touch as (
    select o.member_id,
           min(o.touch_ts) filter (where o.touch_type = 'Welcome') as first_welcome_attempt_ts,
           min(o.touch_ts) filter (where o.touch_type = 'Welcome' and o.is_reached) as welcome_reached_ts,
           count(*) as total_touches,
           count(*) filter (where o.is_reached) as reached_touches
    from staging.stg_outreach o group by 1
),
billing as (
    select member_id, count(*) as rental_months_billed,
           sum(billed_amount_usd) as billed_usd,
           sum(paid_amount_usd) as paid_usd,
           count(*) filter (where invoice_status in ('Denied', 'Written off')) as denied_or_written_off_months
    from staging.stg_invoices group by 1
),
base as (
    select
        m.*,
        i.order_id                                   as initial_order_id,
        i.delivery_date,
        i.headset_id                                 as initial_headset_id,
        h.firmware_version                           as initial_firmware_version,
        h.manufacture_batch                          as initial_batch,
        date_trunc('month', i.delivery_date)::date   as delivery_cohort_month,
        c.order_status                               as current_order_status,
        c.return_request_date,
        c.return_reason,
        coalesce(f.replacement_count, 0)             as replacement_count,
        f.avg_days_without_device,
        s.first_session_date, s.last_session_date, s.last_synced_session_date,
        coalesce(s.total_sessions, 0)                as total_sessions,
        s.total_minutes, s.avg_session_minutes,
        coalesce(s.week1_sessions, 0)                as week1_sessions,
        s.week1_avg_minutes,
        s.active_week4, s.active_week8, s.active_week12,
        s.baseline_pain, s.week7_8_pain,
        t.first_welcome_attempt_ts, t.welcome_reached_ts,
        coalesce(t.total_touches, 0)                 as total_touches,
        coalesce(t.reached_touches, 0)               as reached_touches,
        coalesce(b.rental_months_billed, 0)          as rental_months_billed,
        coalesce(b.billed_usd, 0)                    as billed_usd,
        coalesce(b.paid_usd, 0)                      as paid_usd,
        coalesce(b.denied_or_written_off_months, 0)  as denied_or_written_off_months
    from staging.stg_members m
    left join initial_order i using (member_id)
    left join staging.stg_headsets h on h.headset_id = i.headset_id
    left join current_order c using (member_id)
    left join faults f using (member_id)
    left join sess s using (member_id)
    left join touch t using (member_id)
    left join billing b using (member_id)
)
select
    *,
    -- funnel
    delivery_date is not null                                                     as is_delivered,
    date_diff('day', delivery_date, first_session_date)                           as days_to_first_session,
    first_session_date is not null
        and date_diff('day', delivery_date, first_session_date) <= 14             as is_activated,
    delivery_date + to_days(14) <= as_of()                                                 as is_activation_matured,
    -- outreach
    first_welcome_attempt_ts is not null
        and date_diff('hour', delivery_date::timestamp, first_welcome_attempt_ts) <= 60 as welcome_attempted_48h,
    welcome_reached_ts is not null
        and date_diff('hour', delivery_date::timestamp, welcome_reached_ts) <= 60 as welcome_reached_48h,
    -- habit
    case when first_session_date is null then null
         when week1_sessions >= 5 then '5+ sessions'
         when week1_sessions >= 3 then '3 to 4 sessions'
         when week1_sessions = 2 then '2 sessions'
         else '1 session' end                                                     as week1_bucket,
    week1_sessions >= 3                                                           as hit_week1_habit,
    -- retention (only meaningful once the window has fully passed)
    first_session_date + to_days(34) <= as_of()                                            as is_day30_matured,
    first_session_date + to_days(62) <= as_of()                                            as is_day60_matured,
    first_session_date + to_days(90) <= as_of()                                            as is_day90_matured,
    coalesce(active_week4, false)                                                 as retained_day30,
    coalesce(active_week8, false)                                                 as retained_day60,
    coalesce(active_week12, false)                                                as retained_day90,
    -- program outcome
    coalesce(return_reason = 'Program completed', false) or coalesce(total_sessions >= 28
        and date_diff('day', first_session_date, last_session_date) >= 56, false) as completed_program,
    baseline_pain - week7_8_pain                                                  as pain_reduction_points,
    -- engagement status (true, device clock)
    case
        when current_order_status in ('Cancelled', 'Pending verification') then 'Not enrolled'
        when current_order_status = 'In transit' then 'Awaiting delivery'
        when return_reason = 'Program completed' then 'Completed'
        when current_order_status in ('Returned', 'Return requested') then 'Churned'
        when first_session_date is null then 'Never activated'
        when date_diff('day', last_session_date, as_of()) <= 7 then 'Active'
        when date_diff('day', last_session_date, as_of()) <= 21 then 'At risk'
        when date_diff('day', last_session_date, as_of()) <= 45 then 'Lapsed'
        else 'Churned'
    end                                                                           as engagement_status,
    date_diff('day', last_session_date, as_of())                                  as days_since_last_session,
    -- device currently at home?
    current_order_status = 'Delivered'                                            as headset_at_home,
    current_order_status = 'Delivered'
        and (first_session_date is null or date_diff('day', last_session_date, as_of()) > 30)
        and delivery_date + to_days(30) <= as_of()                                as is_idle_headset_30d,
    first_session_date is not null                                                as has_started,
    first_session_date + to_days(6) <= as_of()                                    as is_week1_matured
from base;

-- ---------------------------------------------------------------------
-- fct_member_weeks: one row per activated member per program week (0..26)
-- Powers the cohort retention heatmap. Only fully observed weeks are kept.
-- ---------------------------------------------------------------------
create or replace table marts.fct_member_weeks as
with weeks as (select unnest(range(0, 27)) as program_week),
activity as (
    select member_id, program_week, count(*) as sessions, sum(duration_minutes) as minutes
    from marts.fct_sessions group by 1, 2
)
select
    m.member_id,
    m.delivery_cohort_month,
    date_trunc('month', m.first_session_date)::date        as first_session_cohort_month,
    w.program_week,
    coalesce(a.sessions, 0)                                as sessions,
    coalesce(a.minutes, 0)                                 as minutes,
    coalesce(a.sessions, 0) > 0                            as is_active_week,
    -- the whole first-session cohort month has had time to reach this week
    (last_day(m.first_session_date) + to_days((w.program_week * 7 + 6)::int)) <= as_of() as is_cohort_cell_complete,
    m.insurance_type, m.plan_name, m.primary_condition, m.age_band, m.referral_source,
    m.welcome_reached_48h, m.week1_bucket, m.has_home_wifi, m.initial_firmware_version
from marts.dim_members m
cross join weeks w
left join activity a on a.member_id = m.member_id and a.program_week = w.program_week
where m.first_session_date is not null
  and m.first_session_date + to_days((w.program_week * 7 + 6)::int) <= as_of();

-- ---------------------------------------------------------------------
-- fct_rental_months: one row per billed rental month, with usage in that period
-- ---------------------------------------------------------------------
create or replace table marts.fct_rental_months as
select
    i.*,
    date_trunc('month', i.service_period_start)::date as service_month,
    coalesce(u.sessions, 0)                           as sessions_in_period,
    coalesce(u.sessions, 0) = 0                       as is_zombie_month,
    i.invoice_status in ('Denied', 'Written off')     as is_lost_revenue
from staging.stg_invoices i
left join lateral (
    select count(*) as sessions
    from marts.fct_sessions s
    where s.member_id = i.member_id
      and s.session_date between i.service_period_start and i.service_period_end
) u on true;

-- ---------------------------------------------------------------------
-- fct_orders and fct_outreach: thin wrappers with member attributes
-- ---------------------------------------------------------------------
create or replace table marts.fct_orders as
select
    o.*,
    h.firmware_version,
    h.manufacture_batch,
    date_trunc('month', coalesce(o.delivery_date, o.order_date))::date as order_month,
    date_diff('day', o.order_date, o.delivery_date)                    as days_order_to_delivery,
    case when o.order_status = 'Replaced'
         then date_diff('day', o.return_request_date, o.replacement_date) end as days_without_working_device
from staging.stg_orders o
left join staging.stg_headsets h using (headset_id);

create or replace table marts.fct_outreach as
select
    t.*,
    date_trunc('month', t.touch_ts)::date as touch_month,
    date_diff('hour', m.delivery_date::timestamp, t.touch_ts) as hours_since_delivery,
    c.coach_name
from staging.stg_outreach t
left join marts.dim_members m using (member_id)
left join staging.stg_coaches c on c.coach_id = t.coach_id;

create or replace table marts.dim_coaches as select * from staging.stg_coaches;
create or replace table marts.dim_headsets as select * from staging.stg_headsets;

-- ---------------------------------------------------------------------
-- fct_status_backtest: was the CRM engagement status right at each month end?
-- "Seen" status uses only sessions synced by the snapshot date (what the team saw then).
-- "Actual" status uses every session done by the snapshot date (known now, after late syncs).
-- Offline headsets (no home wifi) sync days later, so they get flagged at risk while still active.
-- ---------------------------------------------------------------------
create or replace table marts.fct_status_backtest as
with snaps as (
    select unnest(generate_series(date '2025-07-31', date '2026-09-30', interval 1 month))::date as snap
),
snaps_eom as (select last_day(snap) as snapshot_date from snaps),
eligible as (
    select m.member_id, m.has_home_wifi, m.insurance_type, m.urbanicity, m.first_session_date, s.snapshot_date
    from marts.dim_members m
    join snaps_eom s
      on m.first_session_date <= s.snapshot_date
     and (m.return_request_date is null or m.return_request_date > s.snapshot_date)
),
last_seen as (
    select e.member_id, e.snapshot_date,
           max(x.session_date) filter (where x.synced_at_ts::date <= e.snapshot_date and x.session_date <= e.snapshot_date) as last_seen_session,
           max(x.session_date) filter (where x.session_date <= e.snapshot_date) as last_actual_session
    from eligible e
    join marts.fct_sessions x on x.member_id = e.member_id
    group by 1, 2
),
classified as (
    select e.*, l.last_seen_session, l.last_actual_session,
           date_diff('day', l.last_seen_session, e.snapshot_date)   as idle_days_seen,
           date_diff('day', l.last_actual_session, e.snapshot_date) as idle_days_actual
    from eligible e join last_seen l using (member_id, snapshot_date)
)
select *,
    case when last_seen_session is null then 'No synced sessions'
         when idle_days_seen <= 7 then 'Active' when idle_days_seen <= 21 then 'At risk'
         when idle_days_seen <= 45 then 'Lapsed' else 'Churned' end   as status_seen,
    case when idle_days_actual <= 7 then 'Active' when idle_days_actual <= 21 then 'At risk'
         when idle_days_actual <= 45 then 'Lapsed' else 'Churned' end as status_actual,
    idle_days_actual <= 7 and (last_seen_session is null or idle_days_seen > 7) as is_false_alarm
from classified;
