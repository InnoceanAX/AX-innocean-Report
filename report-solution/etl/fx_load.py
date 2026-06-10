"""
fx_load  —  report_mart.fx_rates 적재 (통화 정규화 소스)

소스: ECB 기준환율 (frankfurter.app, 무료/키없음). **잠정(provisional)** — 공식 환율 소스 확정 시 교체.
산출: report_mart.fx_rates(date, currency, usd_per_unit, krw_per_unit, source)
      현지통화 1단위 -> USD / KRW 환산계수. 주말·공휴일은 직전 영업일로 forward-fill.

사용법: python fx_load.py <SA_KEY.json>
"""
import sys, os, json, urllib.request, datetime
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT = "innocean-perf-apac-kr"
KEY = sys.argv[1] if len(sys.argv) > 1 else "innocean-perf-apac-kr-40e02bc0d0d8.json"
MART = f"{PROJECT}.report_mart"
SOURCE = "ECB/frankfurter (provisional)"

if os.path.exists(KEY):
    creds = service_account.Credentials.from_service_account_file(KEY)
    client = bigquery.Client(credentials=creds, project=PROJECT)
else:
    client = bigquery.Client(project=PROJECT)

# 1) 마트에서 통화·기간 파악
row = list(client.query(f"""
  SELECT MIN(date) mn, MAX(date) mx,
         ARRAY_AGG(DISTINCT currency IGNORE NULLS) curs
  FROM `{MART}.report_campaign_performance`""").result())[0]
d0, d1, curs = row.mn, row.mx, [c for c in row.curs if c]
curs = sorted(set(curs) | {"USD"})
print(f"range {d0}~{d1}  currencies={curs}")

# 2) ECB 시계열 (base=USD, symbols=KRW + 통화들)
syms = ",".join(sorted(set(curs) | {"KRW"}))
url = f"https://api.frankfurter.app/{d0}..{d1}?base=USD&symbols={syms}"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = json.load(urllib.request.urlopen(req, timeout=60))
rates = data.get("rates", {})  # {date: {CUR: units_per_USD}}
print(f"fetched {len(rates)} dated rate sets from ECB")

# 3) 전체 날짜 span 으로 forward-fill
def drange(a, b):
    cur = a
    while cur <= b:
        yield cur
        cur += datetime.timedelta(days=1)

rows, last = [], None
for d in drange(d0, d1):
    key = d.isoformat()
    if key in rates:
        last = rates[key]
    if not last:
        continue  # 시작 전 공백
    krw = last.get("KRW")
    for cur in curs:
        per_usd = 1.0 if cur == "USD" else last.get(cur)
        if not per_usd or not krw:
            continue
        rows.append({
            "date": key, "currency": cur,
            "usd_per_unit": 1.0 / per_usd,           # 현지 1단위 -> USD
            "krw_per_unit": krw / per_usd,           # 현지 1단위 -> KRW
            "source": SOURCE,
        })

# 4) 적재 (CREATE OR REPLACE)
schema = [
    bigquery.SchemaField("date", "DATE"),
    bigquery.SchemaField("currency", "STRING"),
    bigquery.SchemaField("usd_per_unit", "FLOAT"),
    bigquery.SchemaField("krw_per_unit", "FLOAT"),
    bigquery.SchemaField("source", "STRING"),
]
tbl = bigquery.Table(f"{MART}.fx_rates", schema=schema)
tbl.time_partitioning = bigquery.TimePartitioning(field="date")
client.delete_table(f"{MART}.fx_rates", not_found_ok=True)
client.create_table(tbl)
job = client.load_table_from_json(rows, f"{MART}.fx_rates",
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"))
job.result()
print(f"loaded {len(rows):,} fx rows -> {MART}.fx_rates")
for r in client.query(f"SELECT currency, COUNT(*) n, MIN(date) mn, MAX(date) mx FROM `{MART}.fx_rates` GROUP BY 1 ORDER BY 1").result():
    print(f"  {r.currency}: {r.n} days {r.mn}~{r.mx}")
