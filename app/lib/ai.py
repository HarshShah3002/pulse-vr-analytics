"""
AI layer (OpenRouter). Three jobs:
  1. Briefings: turn the fact sheet into a short memo for a specific audience.
  2. Fact check: verify every number the AI wrote against the data.
  3. Ask Pulse: plain-English question -> read-only SQL on the marts -> plain-English answer.
Without an API key, template briefings and curated example questions keep the app fully usable.
"""
from __future__ import annotations

import re

import pandas as pd
import requests

from lib.db import AS_OF_LABEL, secret
from lib.facts import facts_table, fd
from lib.metrics import DEFINITIONS

DEFAULT_MODEL = "~anthropic/claude-sonnet-latest"
URL = "https://openrouter.ai/api/v1/chat/completions"


def api_key() -> str | None:
    return secret("OPENROUTER_API_KEY")


def model_name() -> str:
    return secret("OPENROUTER_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def chat(messages: list[dict], max_tokens: int = 4000, temperature: float = 0.2) -> str:
    key = api_key()
    if not key:
        raise RuntimeError("No OPENROUTER_API_KEY configured.")
    r = requests.post(
        URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "X-Title": "Pulse VR Engagement Analytics"},
        json={"model": model_name(), "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
              "reasoning": {"effort": "low", "exclude": True}},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter returned {r.status_code}: {r.text[:300]}")
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):  # some models return a list of text parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not content or not str(content).strip():
        raise RuntimeError(f"The model returned an empty answer (finish reason: {choice.get('finish_reason')}). "
                           "Try again, or switch OPENROUTER_MODEL.")
    return str(content).strip()


# ---------------------------------------------------------------------------
# Briefings
# ---------------------------------------------------------------------------
AUDIENCES = {
    "Executive team": "Founders and leadership. Care about growth, member outcomes, revenue at risk, and the 2 or 3 decisions that matter most this month.",
    "Operations": "Fulfillment, device logistics, and billing. Care about device faults, replacement speed, idle headsets to retrieve, returns, and claim denials.",
    "Care team": "Peer coach managers. Care about who to call this week, the 48-hour welcome call, the first week of use, and statuses they can trust.",
    "Product": "Product and clinical content. Care about which modules work, session length, the first-week experience, and why members stop.",
    "Partnerships": "The team that talks to health plans. Care about engagement, retention, completion, and outcomes they can put in front of a payer.",
}

SYSTEM = f"""You are the analytics partner for Lumora Health, which rents at-home VR therapy headsets
(CBT for chronic pain and anxiety) billed to insurance as monthly equipment rental, with remote peer coaches.
Data snapshot: {AS_OF_LABEL}. The data is simulated to mirror a real program.

Rules:
- Use ONLY numbers from the fact sheet. Never compute new percentages or totals. Copy numbers exactly as displayed.
- Write for a busy non-technical reader: short sentences, no jargon, no statistics terms.
- Say "is linked to", not "causes", unless the fact is a before-and-after policy change.
- No member names or personal details.
- Never use em dashes. Use commas, colons, or periods instead.
- Format in Markdown exactly like this:
**Headline:** one sentence.

**What's happening**
- three bullets, each with one number from the fact sheet

**What to do next**
- three concrete actions, each tied to a finding

**Keep an eye on**
- one bullet
- Under 220 words total."""


def briefing_messages(audience: str, facts: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Audience: {audience}. {AUDIENCES[audience]}\n\nMetric definitions:\n"
                                    + "\n".join(f"- {k}: {v}" for k, v in DEFINITIONS.items())
                                    + f"\n\nFact sheet:\n{facts_table(facts)}\n\nWrite the briefing for this audience."},
    ]


BIG_PICTURE_SYSTEM = SYSTEM.split("- Format in Markdown")[0] + """- Answer the user's question directly. If it asks for next steps, give concrete actions tied to the data.
- Format in Markdown exactly like this:
**Short answer:** one or two sentences that answer the question.

**What the data shows**
- three bullets, each with one number from the fact sheet

**What to do next**
- three concrete actions, each tied to a finding
- Under 220 words total. If the fact sheet cannot answer part of the question, say so plainly."""


def big_picture_messages(question: str, facts: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": BIG_PICTURE_SYSTEM},
        {"role": "user", "content": "Metric definitions:\n" + "\n".join(f"- {k}: {v}" for k, v in DEFINITIONS.items())
                                    + f"\n\nFact sheet:\n{facts_table(facts)}\n\nQuestion from a business leader: {question}"},
    ]


def template_briefing(audience: str, facts: list[dict]) -> str:
    """Deterministic briefing used when no API key is set. Same structure, numbers straight from the facts."""
    F = fd(facts)
    f = {k: v["display"] for k, v in F.items()}

    def module_of(key: str) -> str:
        return F[key]["label"].split(", ", 1)[1].replace(" (highest)", "")

    t = {
        "Executive team": (
            f"The first week decides who stays, and {f['zero_use_share_90d']} of recent rental billing is for months with no headset use.",
            [f"{f['active_now']} members used their headset in the last 7 days; {f['high_risk']} engaged members are at high risk of stopping in the next 30 days.",
             f"Activation for Jul to Sep deliveries is {f['activation_recent']} (vs {f['activation_prior']} for Apr to Jun). After the 48-hour welcome call SLA, activation rose {F['outreach_sla']['value'] * 100:.0f} points across all new members.",
             f"Members with 5+ sessions in their first week stay at day 30 at {f['d30_week1_five']}, vs {f['d30_week1_one']} with a single session."],
            ["Make the first week the priority: set a goal of 3+ sessions and track it weekly.",
             f"Have ops retrieve or re-engage the {f['idle_headsets']} idle headsets; {f['zero_use_billed_90d']} was billed for zero-use months in 90 days.",
             "Use the weekly risk list to focus coach calls on the members most likely to stop."],
            f"Device quality: firmware 4.2.0 failed at {f['fault_bad_fw']} vs {f['fault_other_fw']} for other versions."),
        "Operations": (
            f"{f['idle_headsets']} headsets are sitting idle at members' homes while billing continues.",
            [f"{f['zero_use_billed_90d']} of rental was billed for zero-use months in the last 90 days ({f['zero_use_share_90d']} of billing).",
             f"Firmware 4.2.0 failed at {f['fault_bad_fw']}, vs {f['fault_other_fw']} for other versions.",
             f"Replacements in Feb to Mar left members {f['downtime_slow']} days without a headset, vs {f['downtime_normal']} days in other months."],
            ["Run a retrieval or re-engagement sweep at 30 days idle instead of waiting.",
             "Hold a replacement buffer so turnaround never exceeds a week, even during a bad batch.",
             f"Work with the plan that denies most claims ({f['top_denial_plan_rate']}) on prior authorization."],
            f"{f['avoidable_return_share']} of returned headsets were avoidable exits (non-use, never started, discomfort, device issues)."),
        "Care team": (
            f"{f['high_risk']} members are flagged high risk this week; calling the riskiest 20% reaches {f['model_top20_capture']} of upcoming drop-offs.",
            [f"High-risk members stop at {f['lapse_rate_high']} within 30 days, vs {f['lapse_rate_low']} for low-risk members.",
             f"Members with 5+ week-1 sessions stay at {f['d30_week1_five']} at day 30, vs {f['d30_week1_one']} with one session.",
             f"The CRM showed {f['crm_false_alarm_nowifi']} of truly active members without home wifi as inactive, because their sessions sync late."],
            ["Work the call list from the top; each row includes the reason and a suggested opener.",
             "Aim for 3+ sessions in the first week: call on day 2 or 3 if a member has done fewer than 2.",
             "Before calling a 'lapsed' member without wifi, check when their headset last synced."],
            f"Welcome calls within 48 hours rose from {f['attempt48_pre']} to {f['attempt48_post']} of new members after the SLA; keep it there."),
        "Product": (
            "How often members use the headset in week one matters more than how long each session lasts.",
            [f"Day-30 retention is {f['d30_week1_five']} for 5+ week-1 sessions vs {f['d30_week1_one']} for one session.",
             f"Week-1 sessions averaging 8 to 10 minutes retain at {f['d30_minutes_sweet']}, vs {f['d30_minutes_short']} under 6 minutes and {f['d30_minutes_long']} at 10+ minutes.",
             f"{module_of('best_completion_module')} has the highest completion ({f['best_completion_module']}); "
             f"{module_of('best_relief_module')} gives the most in-session pain relief ({f['best_relief_module']} points on a 0 to 10 scale)."],
            ["Design the first week as short, frequent wins of about 8 to 10 minutes.",
             "Add a gentle day-2 and day-4 prompt inside the headset.",
             "Look at why very long sessions are linked to lower retention (fatigue or discomfort)."],
            f"{f['avoidable_return_share']} of returns are avoidable, including discomfort and never starting."),
        "Partnerships": (
            f"The program keeps members engaged: {f['d30_recent']} of recent starters are still active at day 30.",
            [f"{f['active_now']} members are actively using the program this week.",
             f"{f['completion_rate']} of members who start complete the 8-week program.",
             f"After the 48-hour welcome call SLA, activation rose {F['outreach_sla']['value'] * 100:.0f} points across all new members."],
            ["Lead payer conversations with day-30 retention and completion, not enrollment counts.",
             "Show the proactive retrieval process for unused headsets; it protects the plan's spend.",
             "Offer plans a quarterly engagement report built from these same definitions."],
            f"Unused months are {f['zero_use_share_90d']} of recent billing; address this before a plan raises it."),
    }
    head, happening, todo, watch = t[audience]
    return (f"**Headline:** {head}\n\n**What's happening**\n" + "\n".join(f"- {h}" for h in happening)
            + "\n\n**What to do next**\n" + "\n".join(f"- {a}" for a in todo) + f"\n\n**Keep an eye on**\n- {watch}")


# ---------------------------------------------------------------------------
# Fact check
# ---------------------------------------------------------------------------
STRUCTURAL = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 20, 21, 28, 30, 34, 45, 48, 56, 60, 62, 90, 100}
MONTH_DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?!\d)(,?\s+\d{4})?", re.I)
YEAR = re.compile(r"\b20\d\d\b")
FIRMWARE = re.compile(r"\b\d+\.\d+\.\d+\b")
NUM = re.compile(r"(\$)?(\d[\d,]*(?:\.\d+)?)\s?(%|K\b|M\b|k\b|m\b|percentage points|points|pts)?")


def allowed_from_facts(facts: list[dict]) -> list[tuple[float, str]]:
    out = []
    for f in facts:
        v = f["value"]
        if v is None:
            continue
        if f["kind"] in ("pct", "pts"):
            out.append((abs(v) * 100, "pct"))
        elif f["kind"] == "usd":
            out.append((v, "usd"))
        else:
            out.append((v, "num"))
    return out


def allowed_from_frame(df: pd.DataFrame) -> list[tuple[float, str]]:
    out = []
    for c in df.select_dtypes("number").columns:
        for v in df[c].dropna().head(200):
            v = float(v)
            out.append((v, "num"))
            if -1 <= v <= 1:
                out.append((abs(v) * 100, "pct"))
            out.append((v, "usd"))
    return out


def fact_check(text: str, allowed: list[tuple[float, str]]) -> list[dict]:
    clean = FIRMWARE.sub(" ", MONTH_DATE.sub(" ", YEAR.sub(" ", text)))
    results = []
    for m in NUM.finditer(clean):
        dollar, raw, unit = m.group(1), m.group(2), (m.group(3) or "").strip()
        try:
            x = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit in ("K", "k"):
            x *= 1_000
        elif unit in ("M", "m"):
            x *= 1_000_000
        is_points = unit in ("percentage points", "points", "pts")
        is_pct = unit == "%" or is_points
        if not dollar and not is_pct and x in STRUCTURAL:
            continue
        ok = False
        for a, kind in allowed:
            if is_pct and kind == "pct" and abs(a - x) <= 0.6:
                ok = True
            elif dollar and kind == "usd" and a and abs(a - x) / abs(a) <= 0.03:
                ok = True
            elif not dollar and (not is_pct or is_points) and kind == "num" and (abs(a - x) <= 0.06 or (a and abs(a - x) / abs(a) <= 0.01)):
                ok = True
            if ok:
                break
        results.append({"number": m.group(0).strip(), "verified": ok})
    return results


# ---------------------------------------------------------------------------
# Ask Pulse: text to SQL
# ---------------------------------------------------------------------------
SCHEMA = """
DuckDB tables (all in schema marts). Snapshot date 2026-10-31.
- marts.dim_members (one row per member): member_id, plan_name, insurance_type (Medicare FFS, Medicare Advantage, Medicaid, Commercial),
  primary_condition, has_comorbid_anxiety, age_band, sex, state, urbanicity, referral_source, intake_tech_comfort (Low/Medium/High),
  has_home_wifi, coach_id, delivery_date, delivery_cohort_month, first_session_date, last_session_date, total_sessions, avg_session_minutes,
  week1_sessions, week1_bucket, week1_avg_minutes, is_delivered, is_activation_matured, is_activated, days_to_first_session, has_started,
  hit_week1_habit, welcome_attempted_48h, welcome_reached_48h, is_day30_matured, retained_day30, is_day60_matured, retained_day60,
  is_day90_matured, retained_day90, completed_program, engagement_status (Active, At risk, Lapsed, Churned, Never activated, Completed,
  Not enrolled, Awaiting delivery), days_since_last_session, headset_at_home, is_idle_headset_30d, initial_firmware_version,
  replacement_count, return_reason, baseline_pain, week7_8_pain, pain_reduction_points, rental_months_billed, billed_usd, paid_usd
- marts.fct_sessions (one row per VR session): session_id, member_id, module, session_name, session_start_ts, session_date,
  duration_minutes, completed_flag, pre_pain_score, post_pain_score, in_session_pain_relief, day_in_program, program_week, time_of_day
- marts.fct_member_weeks (member x program week 0..26): member_id, first_session_cohort_month, program_week, sessions, is_active_week,
  is_cohort_cell_complete, plus segment columns insurance_type, plan_name, primary_condition, age_band, welcome_reached_48h, week1_bucket
- marts.fct_orders (headset shipments): order_id, member_id, order_type (Initial, Replacement), order_status, delivery_date,
  return_request_date, return_reason, firmware_version, manufacture_batch, days_without_working_device
- marts.fct_rental_months (monthly rental claims, HCPCS E1905): invoice_id, member_id, service_month, rental_month_number, payer_plan,
  insurance_type, invoice_status (Paid, Pending, Submitted, Denied, Appealed, Written off), billed_amount_usd, paid_amount_usd,
  sessions_in_period, is_zombie_month (billed with zero sessions), is_lost_revenue
- marts.fct_outreach (coach touches): touch_id, member_id, coach_name, touch_ts, touch_month, channel, touch_type, outcome, is_reached
- marts.ml_member_risk (current engaged members): member_id, coach_name, plan_name, risk_score, risk_tier (High/Medium/Low), reason_1,
  recommended_action, days_since_last_session
"""

SQL_RULES = """Write ONE DuckDB SELECT query that answers the question.
- Only use the marts tables above. Never select first_name, last_name, email, phone, or date_of_birth.
- Activation rate: avg(is_activated::int) where is_delivered and is_activation_matured.
- Day-30 retention: avg(retained_day30::int) where has_started and is_day30_matured (same pattern for day 60 and 90).
- Return rates as decimals between 0 and 1 and name columns in plain English with underscores.
- Include a member count column when comparing groups. Keep results under 50 rows, ordered sensibly.
- If the question is a broad summary (for example "how is the business doing" or "what should we do next")
  that one query cannot answer well, reply with exactly NOT_SQL and nothing else.
Return only the SQL in a ```sql code block."""

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|pragma|install|load|export|import|call|"
                       r"set|truncate|grant|vacuum|checkpoint|use|read_csv\w*|read_parquet|read_json\w*|glob|http\w*)\b", re.I)
PII = re.compile(r"\b(first_name|last_name|email|phone|date_of_birth)\b", re.I)


def extract_sql(text: str) -> str:
    """Pull the SQL out of a model reply: any code block, comments removed, starting at SELECT or WITH."""
    blocks = re.findall(r"```[A-Za-z]*\s*(.*?)```", text, re.S)
    sql = blocks[0] if blocks else text
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)   # block comments
    sql = re.sub(r"--[^\n]*", " ", sql)                # line comments
    start = re.search(r"(?im)^\s*(with|select)\b", sql) or re.search(r"(?i)\b(with|select)\b", sql)
    if start:
        sql = sql[start.start():]
    return sql.strip().rstrip(";").strip()


def check_sql(sql: str) -> str | None:
    """Return an error message if the SQL is not a safe, single, read-only query on the marts."""
    s = sql.strip()
    if not re.match(r"^(select|with)\b", s, re.I):
        return "Only SELECT queries are allowed."
    if ";" in s:
        return "Only one statement is allowed."
    if FORBIDDEN.search(s):
        return "The query uses a command or function that is not allowed."
    if PII.search(s):
        return "The query asks for personal details, which Ask Pulse does not return."
    return None


def question_to_sql(question: str) -> str | None:
    """Return SQL for a data question, or None for a big-picture question better answered by a briefing."""
    out = chat([{"role": "system", "content": SCHEMA + "\n" + SQL_RULES},
                {"role": "user", "content": question}], max_tokens=4000, temperature=0)
    if "NOT_SQL" in out and "select" not in out.lower():
        return None
    return extract_sql(out)


def explain_result(question: str, sql: str, df: pd.DataFrame) -> str:
    return chat([
        {"role": "system", "content": "You explain query results to non-technical business leaders at a VR therapy company. "
                                      "Answer in under 110 words: lead with the direct answer, then what it means. "
                                      "Use only numbers that appear in the result (you may show decimals as percentages). "
                                      "If a group has fewer than 50 members, say the number may be unreliable. Never use em dashes."},
        {"role": "user", "content": f"Question: {question}\n\nSQL:\n{sql}\n\nResult (CSV):\n{df.head(40).to_csv(index=False)}"},
    ], max_tokens=2500, temperature=0.2)


EXAMPLES = {
    "Which health plans have the best day-30 retention?": """
select plan_name, count(*) as members, avg(retained_day30::int) as day30_retention
from marts.dim_members where has_started and is_day30_matured
group by 1 order by day30_retention desc""",
    "How does activation differ by tech comfort at intake?": """
select intake_tech_comfort, count(*) as members, avg(is_activated::int) as activation_rate,
       median(days_to_first_session) as median_days_to_first_session
from marts.dim_members where is_delivered and is_activation_matured
group by 1 order by activation_rate desc""",
    "Which modules do members finish most often?": """
select module, count(*) as sessions, avg(completed_flag::int) as completion_rate, median(duration_minutes) as median_minutes
from marts.fct_sessions group by 1 order by completion_rate desc""",
    "How many high-risk members does each coach have this week?": """
select coach_name, count(*) filter (where risk_tier = 'High') as high_risk_members, count(*) as engaged_members
from marts.ml_member_risk group by 1 order by high_risk_members desc""",
    "Do older members stay engaged as long as younger members?": """
select age_band, count(*) as members, avg(retained_day30::int) as day30_retention,
       avg(retained_day90::int) filter (where is_day90_matured) as day90_retention
from marts.dim_members where has_started and is_day30_matured
group by 1 order by 1""",
}