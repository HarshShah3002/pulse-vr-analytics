"""Sanity checks on raw data: do the headline numbers look like a real guided VR program?"""
from pathlib import Path
import duckdb

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
con = duckdb.connect()
for t in ["members", "orders", "headsets", "sessions", "outreach_touches", "invoices", "coaches"]:
    con.execute(f"create view {t} as select * from read_csv_auto('{RAW / (t + '.csv')}', header=true)")

con.execute("""
create temp table m as
with mem as (select distinct on (member_id) * from members order by member_id, engagement_status = 'Not enrolled'),
init as (select * from orders where order_type = 'Initial' and delivery_date is not null),
s as (select distinct on (session_id) * from sessions),
first_s as (select member_id, min(session_start_ts)::date as fs from s group by 1),
w as (
  select i.member_id, i.delivery_date, f.fs,
         date_diff('day', i.delivery_date, f.fs) as days_to_first,
         (select count(*) from s where s.member_id = i.member_id and s.session_start_ts::date between f.fs and f.fs + 6) as w1,
         (select count(*) from s where s.member_id = i.member_id and s.session_start_ts::date between f.fs + 28 and f.fs + 34) > 0 as ret_d30,
         (select count(*) from s where s.member_id = i.member_id and s.session_start_ts::date between f.fs + 84 and f.fs + 90) > 0 as ret_d90
  from init i left join first_s f using (member_id))
select w.*, mem.insurance_type, mem.age_at_referral, mem.has_home_wifi,
  (select min(touch_ts) from outreach_touches o where o.member_id = w.member_id and o.outcome = 'Reached') as first_reach
from w join mem using (member_id)
""")

def q(title, sql):
    print("\n== " + title)
    print(con.execute(sql).df().to_string(index=False))

q("Activation (first session within 14 days of delivery), mature members",
  "select count(*) n, round(avg((days_to_first <= 14)::int),3) act14, round(avg((fs is not null)::int),3) ever, round(median(days_to_first),1) med_days from m where delivery_date <= date '2026-10-01'")
q("Day-30 and day-90 retention among activated (mature cohorts)",
  "select round(avg(ret_d30::int),3) d30, (select round(avg(ret_d90::int),3) from m where fs <= date '2026-07-15') d90 from m where fs <= date '2026-09-20'")
q("Week-1 sessions vs day-30 retention",
  "select least(w1,5) w1_bucket, count(*) n, round(avg(ret_d30::int),3) d30 from m where fs <= date '2026-09-20' group by 1 order by 1")
q("Reached within 48h vs activation (naive)",
  "select (date_diff('hour', delivery_date::timestamp, first_reach) <= 60) reached48, count(*) n, round(avg((days_to_first<=14)::int),3) act14, round(avg(ret_d30::int),3) d30 from m where delivery_date <= date '2026-09-20' group by 1")
q("Sessions: duration minutes + completion by module",
  "select module, count(*) n, round(median(duration_seconds)/60,1) med_min, round(avg(completed_flag::int),3) completion from sessions group by 1 order by n desc")
q("Sessions per active member-week",
  "select round(count(*)/count(distinct member_id || date_trunc('week', session_start_ts)::varchar),2) from sessions")
q("CRM engagement status mix",
  "select engagement_status, count(*) n from members group by 1 order by 2 desc")
q("Return reasons", "select return_reason, count(*) n from orders where return_reason is not null group by 1 order by 2 desc")
q("Fault/replacement rate by firmware",
  "select h.firmware_version, count(*) n, round(avg((o.order_status='Replaced')::int),3) replaced from orders o join headsets h using (headset_id) group by 1 order by 1")
q("Wifi: median sync lag hours",
  "select m.has_home_wifi, round(median(date_diff('minute', s.session_start_ts, s.synced_at_ts))/60,1) med_lag_h from sessions s join (select distinct member_id, has_home_wifi from members) m using (member_id) group by 1")
q("Invoice status", "select invoice_status, count(*) n from invoices group by 1 order by 2 desc")
q("Monthly deliveries", "select date_trunc('month', delivery_date) mo, count(*) from orders where order_type='Initial' and delivery_date is not null group by 1 order by 1")
