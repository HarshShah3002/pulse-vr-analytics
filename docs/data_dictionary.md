# Data Dictionary

Snapshot date: **2026-10-31**. All data is simulated (see `assumptions.md`). Names, emails and phone numbers are fake (emails use `example.com`, phones use the fictional 555 exchange).

## Raw tables (what the source systems export)

These mirror the three source systems a VR therapy program typically runs on: a CRM (members), an order and billing system (orders, invoices), and the headset platform (sessions).

### members (CRM)
| Column | Description |
|---|---|
| member_id | Member key used across all systems |
| crm_id | CRM record id. About 1.5% of members have two CRM records (re-referrals) |
| first_name, last_name, email, phone | Contact details. ~4.5% have no phone. Some emails have stray spaces or uppercase |
| date_of_birth, age_at_referral, sex | Demographics |
| state, urbanicity | Location. Some states arrive lowercase |
| insurance_type, plan_name | Medicare FFS, Medicare Advantage, Medicaid, Commercial; 8 plans |
| primary_condition, secondary_condition | Program track; secondary is anxiety for comorbid pain members |
| referral_source | Provider referral, Health plan outreach, Web self-referral |
| intake_tech_comfort | Self-reported at intake: Low, Medium, High |
| has_home_wifi | False means the headset syncs sessions later |
| coach_id | Assigned peer coach |
| referral_date, onboarding_date | Referral received; insurance verified and enrolled |
| first_session_date, first_vr_session_ts, last_vr_session_ts | CRM rollups from **synced** sessions only |
| engagement_status | CRM status from synced sessions and return data |

### orders (order management)
| Column | Description |
|---|---|
| order_id, member_id, headset_id | Keys |
| order_type | Initial or Replacement |
| order_date, ship_date, delivery_date | Fulfillment dates |
| order_status | Delivered, Replaced, Returned, Return requested, In transit, Cancelled, Pending verification |
| cancel_reason | Insurance not verified |
| return_request_date, return_received_date, return_reason | Return flow |
| replacement_date, replacement_reason | Set on the faulty order when its replacement arrived |

### invoices (billing)
One row per monthly rental claim (HCPCS E1905, capped rental, max 13 months). Columns: invoice_id, order_id, member_id, rental_month_number, service_period_start/end, hcpcs_code, billed_amount_usd, paid_amount_usd, payer_plan, insurance_type, invoice_status (Paid, Pending, Submitted, Denied, Appealed, Written off). Amounts are illustrative.

### sessions (headset platform)
| Column | Description |
|---|---|
| session_id, member_id, headset_id | Keys. ~1.2% of rows are duplicate sync retries |
| module, session_name | 8 modules, 30 named experiences |
| session_start_ts, session_end_ts, duration_seconds | Real headset time. ~2.5% are accidental launches under 60 seconds |
| completed_flag | Finished the experience vs exited early |
| pre_pain_score, post_pain_score | 0 to 10, optional prompt for pain members |
| synced_at_ts | When the CRM received it. Days later for headsets without wifi |

### outreach_touches (coach CRM activity)
touch_id, member_id, coach_id, touch_ts, channel (Call, SMS, Email), touch_type (Welcome, Setup help, Device support, Check-in, Re-engagement nudge, Program completion), outcome (Reached, Voicemail, No answer, Delivered, Sent).

### headsets, coaches
headset_id, model, firmware_version, manufacture_batch, first_ship_date. coach_id, coach_name, hire_date.

## Marts (what Omni reads)

| Table | Grain | Purpose |
|---|---|---|
| dim_members | member | Full journey: funnel flags, outreach timing, week-1 habit, retention flags, status, device, billing, pain outcome |
| fct_sessions | session | Clean sessions with day and week in program, time of day |
| fct_member_weeks | member x program week (0 to 26) | Cohort retention heatmap, with a completeness flag |
| fct_orders | shipment | Faults, returns, replacement turnaround |
| fct_rental_months | invoice | Billing, denials, months billed with zero use |
| fct_outreach | coach touch | Outreach volume and reach |
| fct_status_backtest | member x month end | CRM status shown then vs actual status |
| dim_coaches, dim_headsets | lookup | |

## Metric definitions
| Metric | Definition |
|---|---|
| Activated | First session within 14 days of delivery (members delivered 14+ days before snapshot) |
| Week-1 habit | 3+ sessions in the 7 days starting with the first session |
| Retained at day 30 / 60 / 90 | At least one session in days 28 to 34 / 56 to 62 / 84 to 90 after the first session; only matured members count |
| Engagement status | Active (≤7 days since last session), At risk (8 to 21), Lapsed (22 to 45), Churned (>45 or returned), plus Never activated, Completed, Not enrolled, Awaiting delivery |
| Reached within 48h | Coach spoke with the member within 48h of delivery (60h tolerance for weekends) |
| Completed program | 28+ sessions spanning 8+ weeks, or returned after completion |
| Zombie rental month | Billed rental month with zero sessions |
| Idle headset | At home, delivered 30+ days ago, no session in 30+ days |
| CRM false alarm | Truly active at month end, but the CRM (synced data only) showed not active |
