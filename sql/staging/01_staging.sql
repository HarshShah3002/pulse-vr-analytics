-- =====================================================================
-- STAGING: clean the raw CRM / ops / device exports. One model per source.
-- Rules: fix types and casing, remove duplicates, add data-quality flags.
-- Nothing business-specific happens here; that lives in marts.
-- =====================================================================
create schema if not exists staging;

-- Members: the CRM holds duplicate records when a member is re-referred.
-- Keep the enrolled record (it carries onboarding data); normalize text fields.
create or replace table staging.stg_members as
with ranked as (
    select *,
           row_number() over (
               partition by member_id
               order by (onboarding_date is null), (engagement_status = 'Not enrolled'), crm_id
           ) as rn,
           count(*) over (partition by member_id) as crm_record_count
    from raw.members
)
select
    member_id,
    crm_id,
    crm_record_count,
    first_name,
    last_name,
    lower(trim(email))                         as email,
    phone,
    phone is not null                          as has_phone_on_file,
    date_of_birth::date                        as date_of_birth,
    age_at_referral,
    case
        when age_at_referral < 50 then 'Under 50'
        when age_at_referral < 65 then '50 to 64'
        when age_at_referral < 75 then '65 to 74'
        when age_at_referral < 85 then '75 to 84'
        else '85+'
    end                                        as age_band,
    sex,
    upper(trim(state))                         as state,
    urbanicity,
    insurance_type,
    plan_name,
    primary_condition,
    secondary_condition,
    secondary_condition is not null            as has_comorbid_anxiety,
    referral_source,
    intake_tech_comfort,
    has_home_wifi,
    coach_id,
    referral_date::date                        as referral_date,
    onboarding_date::date                      as onboarding_date,
    first_vr_session_ts::timestamp             as crm_first_session_ts,
    last_vr_session_ts::timestamp              as crm_last_session_ts,
    engagement_status                          as crm_engagement_status
from ranked
where rn = 1;

create or replace table staging.stg_orders as
select
    order_id,
    member_id,
    order_type,
    headset_id,
    order_date::date            as order_date,
    ship_date::date             as ship_date,
    delivery_date::date         as delivery_date,
    order_status,
    cancel_reason,
    return_request_date::date   as return_request_date,
    return_received_date::date  as return_received_date,
    return_reason,
    replacement_date::date      as replacement_date,
    replacement_reason
from raw.orders;

create or replace table staging.stg_headsets as
select
    headset_id,
    model,
    firmware_version,
    manufacture_batch,
    first_ship_date::date as first_ship_date
from raw.headsets;

-- Sessions: offline headsets retry their sync, creating duplicate rows.
-- Keep the first sync per session_id. Flag accidental launches (< 60s).
create or replace table staging.stg_sessions as
with dedup as (
    select *,
           row_number() over (partition by session_id order by synced_at_ts) as rn
    from raw.sessions
)
select
    session_id,
    member_id,
    headset_id,
    module,
    session_name,
    session_start_ts::timestamp                      as session_start_ts,
    session_end_ts::timestamp                        as session_end_ts,
    session_start_ts::date                           as session_date,
    duration_seconds,
    round(duration_seconds / 60.0, 2)                as duration_minutes,
    completed_flag,
    duration_seconds < 60                            as is_accidental_launch,
    pre_pain_score,
    post_pain_score,
    pre_pain_score - post_pain_score                 as in_session_pain_relief,
    synced_at_ts::timestamp                          as synced_at_ts,
    date_diff('hour', session_start_ts::timestamp, synced_at_ts::timestamp) as sync_lag_hours
from dedup
where rn = 1;

create or replace table staging.stg_outreach as
select
    touch_id,
    member_id,
    coach_id,
    touch_ts::timestamp as touch_ts,
    channel,
    touch_type,
    outcome,
    outcome = 'Reached' as is_reached
from raw.outreach_touches;

create or replace table staging.stg_invoices as
select
    invoice_id,
    order_id,
    member_id,
    rental_month_number,
    service_period_start::date as service_period_start,
    service_period_end::date   as service_period_end,
    hcpcs_code,
    billed_amount_usd,
    paid_amount_usd,
    payer_plan,
    insurance_type,
    invoice_status
from raw.invoices;

create or replace table staging.stg_coaches as
select coach_id, coach_name, hire_date::date as hire_date
from raw.coaches;
