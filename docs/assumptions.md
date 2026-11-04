# Simulation Assumptions

The dataset is simulated because real member-level healthcare data is protected. Instead of random columns, each member is simulated day by day through a realistic journey, and the business rules below shape behavior. Every analysis, SQL model and Omni definition in this repo would run unchanged on a real export with the same tables.

## Scale and timeline
- Referrals from May 2025 to Oct 20 2026, growing about 6% per month (about 4,500 referrals, 4,250 headsets delivered).
- Snapshot date 2026-10-31.

## How members behave
| Driver | How it works |
|---|---|
| Hidden motivation | Each member has an unobserved engagement propensity, higher for provider referrals and tech-comfortable members, lower for the very old and web self-referrals. It drives starting, frequency, drop-off **and** whether they pick up the phone. This creates realistic confounding. |
| 48-hour welcome call | Reaching a member within 48h of delivery raises the chance they start and shortens time to first session; it also slightly lowers early drop-off. Whether a call is attempted in 48h depends on coach capacity that month. |
| Week-1 habit | After the first week, drop-off risk scales with week-1 sessions (1 session: about 2.3x baseline, 5+: about 0.55x). |
| Drop-off timing | Daily drop-off risk is highest in the first 2 weeks, lower during weeks 3 to 8, slightly up after the program. |
| Re-engagement | Coaches nudge lapsed members around day 12 of inactivity; about 27% of reached members come back at reduced frequency. |
| Discomfort | 5 to 11% (higher age 78+) feel discomfort or motion sickness early; many drop or return the headset. |
| Program | 8-week core program; completers (28+ sessions by week 8) either return the headset or keep using it lightly. |
| Rental cap | Capped rental ends at 13 months; headset is collected. |

## Business events
| Event | Dates | Effect |
|---|---|---|
| Holiday surge | Nov 2025 to Jan 2026 | 48h welcome-call attempts fell from about 60% to about 35% |
| Faulty firmware 4.2.0 (batch B07) | Shipped Jan 15 to Apr 30 2026 | Fault rate about 20% vs 2 to 3% |
| Slow replacements | Feb to Mar 2026 | 10 to 21 days without a working headset vs 4 to 9 |
| 48-hour welcome call SLA | From Jun 1 2026 | About 88% of welcome calls attempted within 48h; retrieval sweeps more consistent |

## Operations and billing
- Inactive headsets are retrieved in sweeps at 30, 60 and 100 days idle (about 52% each sweep before the SLA, 68% after); never-started headsets at 30, 60, 90 days.
- Billing: one E1905 rental claim per 30 days while the headset is with the member, stopping at the return request. Amount $195/month (illustrative). Denial rates vary by plan (one MA plan has prior-auth friction).

## Data quality issues injected on purpose
Duplicate CRM records (1.5%), missing phones (4.5%), stray spaces and uppercase in emails, lowercase state codes, duplicate session rows from sync retries (1.2%), accidental launches under 60 seconds (2.5%), and offline headsets syncing days late.

## Calibration results
| Metric | Simulated | Reference point |
|---|---|---|
| Median session length | 8 min | Commercial VR pain programs use short sessions of about 6 minutes |
| Members who ever start | 81% | Guided, coach-supported program |
| Activation (first session in 14 days) | 79% | |
| Day-30 retention of starters | 68% | A CBT chronic pain app reported 70% 30-day retention; consumer mental health apps are about 3% |
| Day-90 retention | 38% | Most drop-off in the first weeks, consistent with digital health literature |
| Sessions per active week | 2.8 | |
| 8-week completion (starters) | 51% | |
| Months billed with zero use | 34% | |
| Offline members falsely shown inactive | 44% | |
