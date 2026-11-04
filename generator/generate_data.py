"""
Pulse: synthetic data generator for an at-home VR therapy program.

Simulates the full member journey of a fictional company ("Lumora Health")
that rents VR CBT headsets to members for chronic pain and anxiety, billed as
monthly DME rental (up to 13 months), with remote peer coaches doing outreach.

Every member is simulated day by day: referral -> insurance check -> headset
delivery -> welcome outreach -> first session -> habit formation or drop-off ->
nudges / reactivation -> program completion, return, or a "zombie rental"
(headset kept and billed but unused).

Business mechanics built in (and documented in docs/assumptions.md):
  1. Latent engagement propensity drives most behavior (and confounds outreach).
  2. Reaching a member within 48h of delivery speeds activation and lowers early drop-off.
  3. Sessions in the first 7 days after the first session change long-run drop-off risk.
  4. A firmware batch shipped Jan to Apr 2026 fails far more often; replacements were slow in Feb/Mar.
  5. Members without home wifi store sessions offline and sync late, so the CRM under-reports them.
  6. Inactive headsets are only sometimes retrieved, so some keep being billed.
  7. In June 2026 the company introduced a 48-hour welcome call SLA.

Real-world mess is injected on purpose (duplicates, missing phones, sync retries,
aborted sessions, inconsistent casing) so the staging layer has real work to do.

Usage:  python generator/generate_data.py  [--members-scale 1.0] [--seed 42]
Output: data/raw/*.csv
"""
from __future__ import annotations

import argparse
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

AS_OF = date(2026, 10, 31)
START = date(2025, 5, 1)
LAST_ENROLL = date(2026, 10, 20)
RENTAL_CAP_MONTHS = 13
MONTHLY_RENTAL_USD = 195.00  # illustrative, not a real fee schedule amount

OUT = Path(__file__).resolve().parents[1] / "data" / "raw"


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
PAYERS = [
    # (insurance_type, plan_name, share, denial_rate)
    ("Medicare FFS", "Original Medicare", 0.38, 0.05),
    ("Medicare Advantage", "Summit Senior Advantage", 0.14, 0.07),
    ("Medicare Advantage", "Lakeshore Medicare Plus", 0.12, 0.16),  # prior-auth friction
    ("Medicare Advantage", "Keystone Golden Choice", 0.09, 0.08),
    ("Medicaid", "Prairie Community Care (Medicaid MCO)", 0.08, 0.11),
    ("Medicaid", "Bluegrass Medicaid Partners", 0.05, 0.12),
    ("Commercial", "Cascade Employer PPO", 0.08, 0.10),
    ("Commercial", "Meridian Choice HMO", 0.06, 0.13),
]

STATES = [("FL", .14), ("TX", .12), ("CA", .10), ("PA", .07), ("OH", .07), ("IN", .06),
          ("GA", .06), ("NC", .06), ("AZ", .05), ("MI", .05), ("NY", .05), ("KY", .04),
          ("TN", .04), ("MD", .04), ("WI", .03), ("NM", .02)]
RURAL_SHARE = {"KY": .45, "NM": .40, "TN": .35, "IN": .30, "WI": .30, "OH": .25, "GA": .25,
               "NC": .28, "MI": .25, "PA": .22, "TX": .18, "FL": .12, "AZ": .15, "CA": .08,
               "NY": .10, "MD": .10}

CONDITIONS = [("Chronic low back pain", .34), ("Chronic neck and joint pain", .15),
              ("Fibromyalgia", .09), ("Post-surgical pain", .08), ("Other chronic pain", .07),
              ("Anxiety and stress", .27)]
PAIN_CONDITIONS = {c for c, _ in CONDITIONS if c != "Anxiety and stress"}

REFERRALS = [("Provider referral", .50), ("Health plan outreach", .30), ("Web self-referral", .20)]

MODULES = {
    # module: (target_minutes, base_completion, session names)
    "Pain Education": (11, .74, ["Understanding Pain Signals", "The Pain and Stress Cycle",
                                  "How the Brain Turns Pain Down", "Pacing Your Day",
                                  "Flare-Up Planning", "Rewiring Pain Pathways"]),
    "Diaphragmatic Breathing": (6, .93, ["Breath Basics", "Box Breathing on the Beach",
                                         "Slow Breath Lagoon", "4-7-8 Night Sky"]),
    "Mindfulness": (9, .86, ["Body Scan in the Forest", "Noticing Without Judging",
                             "Riverbank Awareness", "Compassion for the Body"]),
    "Relaxation Escapes": (8, .90, ["Underwater Escape", "Mountain Sunrise", "Autumn Trail",
                                    "Desert Stars"]),
    "Biofeedback": (7, .84, ["Calm the Waves", "Grow the Garden", "Steady the Flame"]),
    "Anxiety and Stress CBT": (10, .80, ["Catching Anxious Thoughts", "Thought Reframing",
                                         "Worry Time", "Facing Small Fears", "Values Compass"]),
    "Sleep Wind-Down": (12, .78, ["Wind-Down Lake", "Moonlit Cabin", "Rain on the Roof"]),
    "Gentle Movement": (8, .81, ["Seated Stretch Studio", "Balance on the Pier",
                                 "Shoulder Release Garden"]),
}

FIRMWARE_FAULTY = "4.2.0"
FAULTY_WINDOW = (date(2026, 1, 15), date(2026, 4, 30))
SLA_START = date(2026, 6, 1)  # 48-hour welcome call SLA introduced


def month_attempt48_rate(d: date) -> float:
    """Share of new members whose welcome call is attempted within 48h (coach capacity)."""
    if d >= SLA_START:
        return 0.88
    if date(2025, 11, 1) <= d < date(2026, 2, 1):  # holiday volume surge, coaches stretched
        return 0.38
    return 0.60


def module_plan(primary: str, comorbid_anxiety: bool, day_in_program: int, rng) -> str:
    if primary == "Anxiety and stress":
        weights = {"Anxiety and Stress CBT": .32, "Mindfulness": .22, "Diaphragmatic Breathing": .16,
                   "Relaxation Escapes": .12, "Sleep Wind-Down": .10, "Biofeedback": .08}
    else:
        if day_in_program < 14:
            weights = {"Pain Education": .34, "Diaphragmatic Breathing": .28, "Relaxation Escapes": .16,
                       "Mindfulness": .12, "Biofeedback": .10}
        else:
            weights = {"Pain Education": .16, "Diaphragmatic Breathing": .14, "Relaxation Escapes": .18,
                       "Mindfulness": .16, "Biofeedback": .12, "Gentle Movement": .14,
                       "Sleep Wind-Down": .10}
        if comorbid_anxiety:
            weights["Mindfulness"] = weights.get("Mindfulness", 0) + .10
            weights["Anxiety and Stress CBT"] = .10
    keys = list(weights)
    p = np.array([weights[k] for k in keys])
    return keys[rng.choice(len(keys), p=p / p.sum())]


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------
class Sim:
    def __init__(self, seed: int, scale: float):
        self.rng = np.random.default_rng(seed)
        self.fake = Faker("en_US")
        Faker.seed(seed)
        self.scale = scale
        self.members, self.orders, self.headsets = [], [], []
        self.sessions, self.outreach, self.invoices = [], [], []
        self.coaches = self._make_coaches()
        self.n_order = self.n_headset = self.n_session = self.n_touch = self.n_inv = 0

    # ---------- helpers ----------
    def pick(self, items):
        p = np.array([w for _, w in items], dtype=float)
        return items[self.rng.choice(len(items), p=p / p.sum())][0]

    def ts(self, d: date, kind: str = "session") -> datetime:
        if kind == "session":  # morning and evening peaks
            hour = int(self.rng.choice([8, 9, 10, 11, 13, 15, 18, 19, 20, 21],
                                       p=[.10, .13, .11, .07, .07, .07, .11, .13, .13, .08]))
        else:  # coach working hours
            hour = int(self.rng.integers(9, 18))
        return datetime(d.year, d.month, d.day, hour, int(self.rng.integers(0, 60)),
                        int(self.rng.integers(0, 60)))

    def _make_coaches(self):
        rows = []
        hires = [date(2025, 4, 15)] * 5 + [date(2025, 9, 1)] * 3 + [date(2026, 2, 15)] * 2 + [date(2026, 6, 1)] * 4
        for i, h in enumerate(hires, start=1):
            rows.append({"coach_id": f"CO{i:03d}", "coach_name": Faker().first_name() + " " + Faker().last_name()[0] + ".",
                         "hire_date": h, "reach_skill": float(self.rng.normal(0, 0.35))})
        return rows

    def coach_for(self, d: date):
        pool = [c for c in self.coaches if c["hire_date"] <= d]
        return pool[self.rng.integers(len(pool))]

    def new_headset(self, ship: date):
        self.n_headset += 1
        hid = f"HS-{self.n_headset:06d}"
        if FAULTY_WINDOW[0] <= ship <= FAULTY_WINDOW[1] and self.rng.random() < 0.7:
            fw, batch = FIRMWARE_FAULTY, "B07"
        elif ship < date(2025, 12, 1):
            fw, batch = "4.1.3", self.pick([("B04", .5), ("B05", .5)])
        else:
            fw, batch = ("4.3.1", "B09") if ship > FAULTY_WINDOW[1] else ("4.1.3", "B06")
        self.headsets.append({"headset_id": hid, "model": "Lumora XR Kit 2", "firmware_version": fw,
                              "manufacture_batch": batch, "first_ship_date": ship})
        fault_p = 0.21 if fw == FIRMWARE_FAULTY else 0.03
        return hid, fault_p

    def touch(self, member_id, coach_id, when: datetime, channel, ttype, outcome):
        self.n_touch += 1
        self.outreach.append({"touch_id": f"T{self.n_touch:07d}", "member_id": member_id, "coach_id": coach_id,
                              "touch_ts": when, "channel": channel, "touch_type": ttype, "outcome": outcome})

    # ---------- enrollment volume ----------
    def referral_dates(self):
        d, out, i = START, [], 0
        while d <= LAST_ENROLL:
            nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            days = (min(nxt, LAST_ENROLL + timedelta(days=1)) - d).days
            month_days = (nxt - d).days
            n = int(round(150 * (1.06 ** i) * self.scale * self.rng.normal(1, 0.05) * days / month_days))
            for _ in range(n):
                out.append(d + timedelta(days=int(self.rng.integers(days))))
            d, i = nxt, i + 1
        return sorted(out)

    # ---------- one member ----------
    def simulate_member(self, idx: int, referral: date):
        rng, fake = self.rng, self.fake
        mid = f"M{idx:06d}"
        payer_i = rng.choice(len(PAYERS), p=np.array([p[2] for p in PAYERS]) / sum(p[2] for p in PAYERS))
        ins_type, plan, _, denial = PAYERS[payer_i]
        if ins_type.startswith("Medicare"):
            age = int(np.clip(rng.normal(73, 7), 65, 94)) if rng.random() > .12 else int(rng.integers(45, 65))
        elif ins_type == "Medicaid":
            age = int(rng.integers(24, 65))
        else:
            age = int(rng.integers(28, 65))
        sex = "F" if rng.random() < .63 else "M"
        state = self.pick(STATES)
        rural = rng.random() < RURAL_SHARE[state]
        primary = self.pick(CONDITIONS)
        comorbid = primary in PAIN_CONDITIONS and rng.random() < .31
        referral_src = self.pick(REFERRALS)
        wifi_p = .88 - (.22 if ins_type == "Medicaid" else 0) - (.14 if rural else 0) - (.06 if age > 80 else 0)
        has_wifi = rng.random() < wifi_p
        tech = "Low" if rng.random() < (.20 + max(0, age - 70) * .015) else ("High" if rng.random() < .35 else "Medium")
        # latent propensity (never exported)
        z = rng.normal(0, 1) + (.25 if referral_src == "Provider referral" else 0) \
            - (.15 if referral_src == "Web self-referral" else 0) + {"Low": -.35, "Medium": 0, "High": .2}[tech] \
            - (.2 if age > 82 else 0) + (.1 if primary == "Anxiety and stress" else 0)
        phone_valid = rng.random() > .045
        first, last = (fake.first_name_female() if sex == "F" else fake.first_name_male()), fake.last_name()
        dob = date(referral.year - age, int(rng.integers(1, 13)), int(rng.integers(1, 29)))

        m = {"member_id": mid, "crm_id": f"CRM-{int(rng.integers(10**7, 10**8))}", "first_name": first,
             "last_name": last, "email": f"{first}.{last}{int(rng.integers(1, 999))}@example.com".lower(),
             "phone": (f"({int(rng.integers(201, 990))}) 555-{int(rng.integers(1000, 9999))}" if phone_valid else None),
             "date_of_birth": dob, "age_at_referral": age, "sex": sex, "state": state,
             "urbanicity": "Rural" if rural else "Urban/Suburban", "insurance_type": ins_type, "plan_name": plan,
             "primary_condition": primary, "secondary_condition": "Anxiety and stress" if comorbid else None,
             "referral_source": referral_src, "intake_tech_comfort": tech, "has_home_wifi": has_wifi,
             "referral_date": referral}

        # insurance verification / cancellation
        verify = referral + timedelta(days=int(rng.integers(1, 9)))
        cancel_p = .045 + (.05 if plan == "Lakeshore Medicare Plus" else 0)
        coach = self.coach_for(verify)
        m["coach_id"] = coach["coach_id"]
        if rng.random() < cancel_p or verify > AS_OF:
            self.n_order += 1
            self.orders.append({"order_id": f"ORD-{self.n_order:06d}", "member_id": mid, "order_type": "Initial",
                                "headset_id": None, "order_date": referral, "ship_date": None, "delivery_date": None,
                                "order_status": "Cancelled" if verify <= AS_OF else "Pending verification",
                                "cancel_reason": "Insurance not verified" if verify <= AS_OF else None,
                                "return_request_date": None, "return_received_date": None, "return_reason": None,
                                "replacement_date": None, "replacement_reason": None})
            m.update(onboarding_date=None)
            self.members.append(m)
            return
        onboarding = verify
        ship = onboarding + timedelta(days=int(rng.integers(1, 4)))
        delivery = ship + timedelta(days=int(rng.integers(2, 5)) + (int(rng.integers(1, 4)) if rural else 0))
        m["onboarding_date"] = onboarding
        if delivery > AS_OF:
            hid, _ = self.new_headset(ship)
            self.n_order += 1
            self.orders.append({"order_id": f"ORD-{self.n_order:06d}", "member_id": mid, "order_type": "Initial",
                                "headset_id": hid, "order_date": referral, "ship_date": ship, "delivery_date": None,
                                "order_status": "In transit", "cancel_reason": None, "return_request_date": None,
                                "return_received_date": None, "return_reason": None, "replacement_date": None,
                                "replacement_reason": None})
            self.members.append(m)
            return

        # ---------- welcome outreach ----------
        attempt48 = rng.random() < month_attempt48_rate(delivery)
        reach_logit = -.1 + .75 * z + coach["reach_skill"] + (.0 if phone_valid else -1.6)
        reached48 = False
        first_reach_day = None
        t0 = int(rng.integers(0, 2)) if attempt48 else int(rng.integers(3, 9))
        for a in range(3):
            day = t0 + a * int(rng.integers(1, 3))
            when = self.ts(delivery + timedelta(days=day), "coach")
            if when.date() > AS_OF:
                break
            if not phone_valid:
                self.touch(mid, coach["coach_id"], when, "Email", "Welcome", "Sent")
                break
            ok = rng.random() < sigmoid(reach_logit)
            self.touch(mid, coach["coach_id"], when, "Call", "Welcome",
                       "Reached" if ok else ("Voicemail" if rng.random() < .6 else "No answer"))
            if not ok and rng.random() < .5:
                self.touch(mid, coach["coach_id"], when + timedelta(minutes=5), "SMS", "Welcome", "Delivered")
            if ok:
                first_reach_day = day
                reached48 = day <= 2
                break

        # ---------- headset + device faults ----------
        hid, fault_p = self.new_headset(ship)
        orders_for_member = []
        cur = {"order_id": None, "headset_id": hid, "order_type": "Initial", "order_date": referral,
               "ship_date": ship, "delivery_date": delivery}
        fault_day = int(rng.integers(0, 45)) if rng.random() < fault_p else None
        # DOA faults happen on day 0 to 2
        if fault_day is not None and rng.random() < .3:
            fault_day = int(rng.integers(0, 3))
        discomfort = rng.random() < (.05 + (.06 if age >= 78 else 0))

        # ---------- first session ----------
        act_logit = 1.45 + .85 * z + 1.15 * reached48 - (.55 if tech == "Low" else 0) - (.5 if discomfort else 0)
        will_activate = rng.random() < sigmoid(act_logit)
        delay_mean = (1.6 if reached48 else 4.2) + (2.5 if tech == "Low" else 0) + (1.5 if not attempt48 else 0)
        first_day = int(rng.geometric(1 / delay_mean)) - 1 if will_activate else None
        if first_day is not None and first_day > 4 and first_reach_day is None and rng.random() < .55:
            # setup help call for members who have not started by day 5
            self.touch(mid, coach["coach_id"], self.ts(delivery + timedelta(days=5), "coach"), "Call",
                       "Setup help", "Reached" if rng.random() < sigmoid(reach_logit) else "Voicemail")
        elif first_day is None and rng.random() < .7 and delivery + timedelta(days=5) <= AS_OF:
            self.touch(mid, coach["coach_id"], self.ts(delivery + timedelta(days=5), "coach"), "Call",
                       "Setup help", "Reached" if rng.random() < sigmoid(reach_logit) else "No answer")

        # ---------- day by day ----------
        horizon = (AS_OF - delivery).days
        p0 = sigmoid(-.45 + .55 * z + .35 * reached48 + (.2 if tech == "High" else 0) - (.15 if age > 80 else 0))
        base_pain = float(np.clip(rng.normal(6.6, 1.2), 3, 10)) if primary in PAIN_CONDITIONS else None
        responder = rng.normal(1.0, .35)
        sessions_done = 0
        w1 = None
        active = will_activate
        dropped_day = None
        reactivated = False
        completed_day = None
        broken_until = None
        returned_request = None
        return_reason = None
        last_session_day = None
        decided_retrieval = False
        maintenance_after_completion = None
        insurance_hazard = .015 / 365
        death_hazard = (.03 if age >= 75 else .012) / 365 if ins_type.startswith("Medicare") else .002 / 365
        sync_lag_mean = 0 if has_wifi else float(rng.uniform(6, 18))
        next_sync = delivery + timedelta(days=int(rng.exponential(sync_lag_mean))) if not has_wifi else None
        member_sessions = []

        for day in range(horizon + 1):
            today = delivery + timedelta(days=day)
            if returned_request:
                break
            # device fault
            if fault_day is not None and day == fault_day and broken_until is None:
                rep_wait = int(rng.integers(10, 22)) if date(2026, 2, 1) <= today <= date(2026, 3, 31) else int(rng.integers(4, 10))
                broken_until = day + rep_wait
                self.touch(mid, coach["coach_id"], self.ts(today, "coach"), "Call", "Device support", "Reached")
                cur["fault"] = (today, rep_wait)
                if rep_wait > 14 and rng.random() < .3:
                    returned_request, return_reason = today + timedelta(days=rep_wait - 3), "Device issue"
                    continue
            if broken_until is not None and day == broken_until:
                # replacement delivered
                cur["replacement_date"] = today
                orders_for_member.append(cur)
                new_hid, _ = self.new_headset(today - timedelta(days=3))
                cur = {"order_id": None, "headset_id": new_hid, "order_type": "Replacement",
                       "order_date": today - timedelta(days=broken_until - fault_day),
                       "ship_date": today - timedelta(days=3), "delivery_date": today}
                broken_until = -1
            device_ok = broken_until in (None, -1)

            # capped rental ends after 13 months: headset is collected
            if day >= RENTAL_CAP_MONTHS * 30:
                returned_request, return_reason = today, "Rental term ended"
                break
            # exogenous exits
            if rng.random() < insurance_hazard:
                returned_request, return_reason = today, "Insurance change"
                break
            if rng.random() < death_hazard:
                returned_request, return_reason = today, "Deceased"
                break

            if first_day is None or day < first_day:
                # never started: retrieval after 45 days with some probability
                if first_day is None and day in (30, 60, 90) and rng.random() < .6:
                    returned_request, return_reason = today, "Never started"
                continue

            t = day - first_day
            if t == 7 and w1 is None:
                w1 = sum(1 for s in member_sessions if s <= first_day + 6)

            if active:
                # drop-off hazard
                if t < 14:
                    h = .022
                elif t < 56:
                    h = .009
                else:
                    h = .011
                h *= math.exp(-.45 * z) * (.85 if reached48 else 1.0)
                if w1 is not None:
                    h *= 2.3 if w1 <= 1 else 1.4 if w1 == 2 else .8 if w1 <= 4 else .55
                if discomfort and t < 21:
                    h *= 3.5
                if not device_ok:
                    h *= 2.0
                if completed_day is not None:
                    h *= .7
                if t > 3 and rng.random() < h:
                    active = False
                    dropped_day = day
                    if discomfort and t < 21 and rng.random() < .5:
                        returned_request, return_reason = today + timedelta(days=int(rng.integers(2, 8))), "Discomfort or motion sickness"
                    continue
                # session today?
                if device_ok:
                    if completed_day is None:
                        p = p0 * (.62 + .38 * math.exp(-t / 35)) * (1.25 if t == 0 else 1)
                    else:
                        p = p0 * .38
                    if reactivated:
                        p *= .7
                    if t == 0 or rng.random() < p:
                        member_sessions.append(day)
                        last_session_day = day
                        sessions_done += 1
                        # 7% of days have a second session
                        n_today = 2 if rng.random() < .07 else 1
                        for _ in range(n_today):
                            self._emit_session(mid, cur["headset_id"], today, t, primary, comorbid, age,
                                               base_pain, responder, sessions_done, has_wifi, next_sync, sync_lag_mean)
                # program completion at day 56 of program
                if completed_day is None and t == 56 and sessions_done >= 28:
                    completed_day = day
                    self.touch(mid, coach["coach_id"], self.ts(today, "coach"), "Call", "Program completion", "Reached")
                    maintenance_after_completion = rng.random() < .55
                    if not maintenance_after_completion:
                        returned_request, return_reason = today + timedelta(days=int(rng.integers(3, 15))), "Program completed"
                # periodic check-ins
                if t > 0 and t % 14 == 0 and rng.random() < .5:
                    self.touch(mid, coach["coach_id"], self.ts(today, "coach"), "Call", "Check-in",
                               "Reached" if rng.random() < sigmoid(reach_logit + .5) else "Voicemail")
            else:
                idle = day - (last_session_day if last_session_day is not None else first_day)
                # nudge once 10 to 20 days after drop
                if idle == 12 and not reactivated and rng.random() < (.75 if today >= SLA_START else .5):
                    ok = phone_valid and rng.random() < sigmoid(reach_logit)
                    self.touch(mid, coach["coach_id"], self.ts(today, "coach"), "Call" if phone_valid else "SMS",
                               "Re-engagement nudge", "Reached" if ok else ("Voicemail" if phone_valid else "Delivered"))
                    if ok and rng.random() < .27:
                        active, reactivated = True, True
                        first_day = first_day  # keep program clock
                        continue
                # retrieval decision for inactive headsets
                if idle in (30, 60, 100):
                    # ops retrieval sweeps for inactive headsets (inconsistent before the SLA era)
                    if rng.random() < (.68 if today >= SLA_START else .52):
                        returned_request, return_reason = today, "Non-use"

        # ---------- close out orders ----------
        if returned_request and returned_request > AS_OF:
            returned_request, return_reason = None, None
        orders_for_member.append(cur)
        for k, o in enumerate(orders_for_member):
            self.n_order += 1
            o["order_id"] = f"ORD-{self.n_order:06d}"
            is_last = k == len(orders_for_member) - 1
            row = {"order_id": o["order_id"], "member_id": mid, "order_type": o["order_type"],
                   "headset_id": o["headset_id"], "order_date": o["order_date"], "ship_date": o["ship_date"],
                   "delivery_date": o["delivery_date"], "cancel_reason": None, "return_request_date": None,
                   "return_received_date": None, "return_reason": None,
                   "replacement_date": o.get("replacement_date"),
                   "replacement_reason": "Device fault" if o.get("replacement_date") else None}
            if not is_last:
                row["order_status"] = "Replaced"
                row["return_request_date"] = o["fault"][0]
                row["return_received_date"] = min(AS_OF, o["fault"][0] + timedelta(days=int(rng.integers(5, 15))))
                row["return_reason"] = "Device fault (swap)"
            elif returned_request:
                received = returned_request + timedelta(days=int(rng.integers(5, 21)))
                row["return_request_date"] = returned_request
                row["return_received_date"] = received if received <= AS_OF else None
                row["return_reason"] = return_reason
                row["order_status"] = "Returned" if received <= AS_OF else "Return requested"
            else:
                row["order_status"] = "Delivered"
            self.orders.append(row)
            self._bill(mid, row, plan, ins_type, denial)
        self.members.append(m)

    def _emit_session(self, mid, hid, d, t, primary, comorbid, age, base_pain, responder, n_done,
                      has_wifi, next_sync, lag_mean):
        rng = self.rng
        module = module_plan(primary, comorbid, t, rng)
        target, comp, names = MODULES[module]
        start = self.ts(d)
        comp_p = comp - (.06 if age > 80 else 0) + (.03 if t > 21 else 0) - (.08 if t < 3 else 0)
        completed = rng.random() < comp_p
        dur = target * 60 * float(rng.lognormal(0, .18))
        if not completed:
            dur *= float(rng.uniform(.1, .7))
        if rng.random() < .025:  # aborted / accidental launches
            dur, completed = float(rng.uniform(3, 40)), False
        dur = int(round(dur))
        pre = post = None
        if base_pain is not None and module != "Sleep Wind-Down" and rng.random() < .72:
            trend = base_pain - min(2.6, .055 * n_done * responder)
            pre = int(np.clip(round(rng.normal(trend, 1.0)), 0, 10))
            post = int(np.clip(pre - max(0, round(rng.normal(.9 if completed else .3, .7))), 0, 10))
        if has_wifi:
            synced = start + timedelta(seconds=dur + int(rng.integers(20, 600)))
        else:
            # offline: syncs at the member's next wifi window (library, family visit, phone hotspot)
            lag = timedelta(days=float(rng.exponential(lag_mean)))
            synced = start + timedelta(seconds=dur) + lag
        self.n_session += 1
        sid = f"S{self.n_session:08d}"
        row = {"session_id": sid, "member_id": mid, "headset_id": hid, "module": module,
               "session_name": names[rng.integers(len(names))], "session_start_ts": start,
               "session_end_ts": start + timedelta(seconds=dur), "duration_seconds": dur,
               "completed_flag": completed, "pre_pain_score": pre, "post_pain_score": post,
               "synced_at_ts": synced}
        if synced.date() <= AS_OF:
            self.sessions.append(row)
            if rng.random() < .012:  # sync retry duplicates
                dup = dict(row)
                dup["synced_at_ts"] = synced + timedelta(minutes=int(rng.integers(1, 90)))
                self.sessions.append(dup)

    def _bill(self, mid, order, plan, ins_type, denial):
        """Monthly rental invoices while the headset is with the member (capped rental)."""
        if order["delivery_date"] is None:
            return
        end = order["return_request_date"] or AS_OF  # billing stops when pickup is requested
        if order["order_status"] == "Replaced":
            end = order["replacement_date"] or end
        start = order["delivery_date"]
        k = 0
        while k < RENTAL_CAP_MONTHS:
            period_start = start + timedelta(days=30 * k)
            if period_start > end or period_start > AS_OF:
                break
            age_days = (AS_OF - period_start).days
            r = self.rng.random()
            if age_days < 25:
                status = "Pending" if r < .85 else "Submitted"
            elif age_days < 60:
                status = "Paid" if r < .55 else ("Pending" if r < .9 else "Denied")
            else:
                if r < denial:
                    status = "Appealed" if self.rng.random() < .35 else ("Written off" if self.rng.random() < .5 else "Denied")
                else:
                    status = "Paid"
            self.n_inv += 1
            self.invoices.append({"invoice_id": f"INV-{self.n_inv:07d}", "order_id": order["order_id"],
                                  "member_id": mid, "rental_month_number": k + 1,
                                  "service_period_start": period_start,
                                  "service_period_end": period_start + timedelta(days=29),
                                  "hcpcs_code": "E1905", "billed_amount_usd": MONTHLY_RENTAL_USD,
                                  "payer_plan": plan, "insurance_type": ins_type, "invoice_status": status,
                                  "paid_amount_usd": round(MONTHLY_RENTAL_USD * .8, 2) if status == "Paid" else 0.0})
            k += 1

    # ---------- run ----------
    def run(self):
        for i, r in enumerate(self.referral_dates(), start=1):
            self.simulate_member(i, r)
        return self

    # ---------- messiness + export ----------
    def export(self):
        rng = self.rng
        members = pd.DataFrame(self.members)
        orders = pd.DataFrame(self.orders)
        sessions = pd.DataFrame(self.sessions)
        outreach = pd.DataFrame(self.outreach)
        invoices = pd.DataFrame(self.invoices)
        headsets = pd.DataFrame(self.headsets)
        coaches = pd.DataFrame(self.coaches).drop(columns=["reach_skill"])

        # CRM rollups exactly as a CRM would show them: based on SYNCED sessions only
        s_sorted = sessions.drop_duplicates("session_id")
        roll = s_sorted.groupby("member_id").agg(first_vr_session_ts=("session_start_ts", "min"),
                                                 last_vr_session_ts=("session_start_ts", "max"))
        members = members.merge(roll, on="member_id", how="left")
        members["first_session_date"] = members["first_vr_session_ts"].dt.date
        last_order = orders.sort_values(["member_id", "order_id"]).groupby("member_id").tail(1).set_index("member_id")

        def crm_status(r):
            o = last_order.loc[r.member_id]
            if o.order_status in ("Cancelled", "Pending verification"):
                return "Not enrolled"
            if o.order_status == "In transit":
                return "Awaiting delivery"
            if o.return_reason == "Program completed":
                return "Completed"
            if o.order_status in ("Returned", "Return requested"):
                return "Churned"
            if pd.isna(r.last_vr_session_ts):
                return "Never activated"
            idle = (pd.Timestamp(AS_OF) - r.last_vr_session_ts).days
            return "Active" if idle <= 7 else "At risk" if idle <= 21 else "Lapsed" if idle <= 45 else "Churned"
        members["engagement_status"] = members.apply(crm_status, axis=1)

        # --- inject mess ---
        idx = rng.choice(len(members), size=int(len(members) * .015), replace=False)
        dups = members.iloc[idx].copy()
        dups["crm_id"] = [f"CRM-{int(rng.integers(10**7, 10**8))}" for _ in range(len(dups))]
        dups["member_id"] = dups["member_id"]  # same member, second CRM record from a re-referral
        dups["email"] = dups["email"].str.upper()
        dups["engagement_status"] = "Not enrolled"
        members = pd.concat([members, dups], ignore_index=True)
        flip = rng.random(len(members)) < .08
        members.loc[flip, "state"] = members.loc[flip, "state"].str.lower()
        pad = rng.random(len(members)) < .05
        members.loc[pad, "email"] = " " + members.loc[pad, "email"] + " "

        members = members[["member_id", "crm_id", "first_name", "last_name", "email", "phone", "date_of_birth",
                           "age_at_referral", "sex", "state", "urbanicity", "insurance_type", "plan_name",
                           "primary_condition", "secondary_condition", "referral_source", "intake_tech_comfort",
                           "has_home_wifi", "coach_id", "referral_date", "onboarding_date", "first_session_date",
                           "first_vr_session_ts", "last_vr_session_ts", "engagement_status"]]
        members = members.sample(frac=1, random_state=7).reset_index(drop=True)

        OUT.mkdir(parents=True, exist_ok=True)
        for name, df in [("members", members), ("orders", orders), ("headsets", headsets),
                         ("sessions", sessions), ("outreach_touches", outreach), ("invoices", invoices),
                         ("coaches", coaches)]:
            df.to_csv(OUT / f"{name}.csv", index=False)
            print(f"{name:18s} {len(df):>9,d} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--members-scale", type=float, default=1.0)
    a = ap.parse_args()
    Sim(a.seed, a.members_scale).run().export()
