"""
report-mart-builder  —  raw(read-only) -> report_mart (dedicated)

격리 원칙: apac_kr_raw 를 READ 만 한다. 절대 raw 에 쓰지 않는다.
산출: report_mart.report_campaign_performance  (정규화 집행실적, 일x플랫폼x캠페인 grain)
      report_mart.mart_coverage                (플랫폼별 신선도/공백 스냅샷)

Phase 1 적재 플랫폼: Meta / TikTok / DV360  (단일테이블 클린 소스)
다음 반복: Google Ads(CampaignBasicStats+Campaign+Customer x14 MCC) / SA360 / CM360
통화: spend 는 현지통화 그대로 + currency. costs_krw/usd 는 FX 확정 후.
"""
import os, sys
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT = "innocean-perf-apac-kr"
KEY = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SA_KEY", "innocean-perf-apac-kr-40e02bc0d0d8.json")
RAW = f"{PROJECT}.apac_kr_raw"
MART = f"{PROJECT}.report_mart"

# 로컬: SA 키 파일 사용 / Cloud Run Job: ADC(런타임 SA) 사용
if os.path.exists(KEY):
    creds = service_account.Credentials.from_service_account_file(KEY)
    client = bigquery.Client(credentials=creds, project=PROJECT)
else:
    client = bigquery.Client(project=PROJECT)

# ── 1) 통합 집행실적 마트 ───────────────────────────────────────────────
# 소스 = apac_kr_unified.v_perf_unified (수집AI 소유, 읽기전용).
#   이미 통화정규화(spend_krw/usd)·브랜드/마켓 매핑·중복제거(is_excluded) 완료.
#   리포트 마트는 그 위에 얹어 프론트 0402_dm 스키마로 투영(중복로직 없음).
#   is_excluded=TRUE(DV360↔CM360 중복 등) 제외. reach/frequency·ad그레인은 통합뷰 미제공 → NULL(정직).
UNIFIED = f"{PROJECT}.apac_kr_unified.v_perf_unified"
BUILD_PERFORMANCE = f"""
CREATE OR REPLACE TABLE `{MART}.report_campaign_performance`
PARTITION BY date
CLUSTER BY platform, brand_name AS
SELECT
  u.date, u.platform,
  u.brand AS brand_name,
  u.market AS country,
  u.agency,
  CAST(u.advertiser_id AS STRING) AS advertiser_id, u.advertiser_name,
  CAST(u.campaign_id AS STRING) AS campaign_id, u.campaign_name,
  CAST(NULL AS STRING) AS adgroup_id, CAST(NULL AS STRING) AS adgroup_name,
  CAST(NULL AS STRING) AS ad_id, CAST(NULL AS STRING) AS ad_name,
  u.currency,
  u.spend_local AS spend,
  u.spend_krw   AS costs_krw,
  u.spend_usd   AS costs_usd,
  u.revenue_krw,
  u.impressions, u.clicks,
  CAST(NULL AS FLOAT64) AS reach, CAST(NULL AS FLOAT64) AS frequency,
  u.conversions,
  vid.video_views, vid.engagements, vid.video_p25, vid.video_p50, vid.video_p75, vid.video_p100,
  SAFE_DIVIDE(u.clicks, u.impressions)            AS ctr,
  SAFE_DIVIDE(u.spend_local, u.clicks)            AS cpc,
  SAFE_DIVIDE(u.spend_local, u.impressions) * 1000 AS cpm,
  SAFE_DIVIDE(u.spend_krw, u.clicks)              AS cpc_krw,
  SAFE_DIVIDE(u.spend_krw, u.impressions) * 1000  AS cpm_krw,
  SAFE_DIVIDE(u.conversions, u.clicks)            AS conversion_rate,
  SAFE_DIVIDE(u.revenue_krw, u.spend_krw)         AS roas,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM `{UNIFIED}` u
LEFT JOIN (
  SELECT date, platform, CAST(campaign_id AS STRING) campaign_id,
    SUM(video_views) video_views, SUM(engagements) engagements,
    SUM(video_p25) video_p25, SUM(video_p50) video_p50, SUM(video_p75) video_p75, SUM(video_p100) video_p100
  FROM `{PROJECT}.apac_kr_unified.v_perf_unified_video`
  WHERE NOT IFNULL(is_excluded, FALSE) GROUP BY 1,2,3
) vid ON u.date=vid.date AND u.platform=vid.platform AND CAST(u.campaign_id AS STRING)=vid.campaign_id
WHERE u.date IS NOT NULL AND NOT IFNULL(u.is_excluded, FALSE)
"""

# ── 1b) 세그먼트(디바이스/연령/성별) 통합 — v_perf_unified_{device,age,gender} ──
UNI = f"{PROJECT}.apac_kr_unified"
BUILD_SEGMENTS = f"""
CREATE OR REPLACE TABLE `{MART}.report_segments`
PARTITION BY date CLUSTER BY segment_type, platform AS
SELECT date, platform, CAST(campaign_id AS STRING) campaign_id, market AS country, brand AS brand_name,
  'device' AS segment_type, device AS segment_value, impressions, clicks, spend_krw AS costs_krw, revenue_krw, conversions
FROM `{UNI}.v_perf_unified_device` WHERE date IS NOT NULL AND NOT IFNULL(is_excluded,FALSE)
UNION ALL
SELECT date, platform, CAST(campaign_id AS STRING), market, brand,
  'age', age_range, impressions, clicks, spend_krw, revenue_krw, conversions
FROM `{UNI}.v_perf_unified_age` WHERE date IS NOT NULL AND NOT IFNULL(is_excluded,FALSE)
UNION ALL
SELECT date, platform, CAST(campaign_id AS STRING), market, brand,
  'gender', gender, impressions, clicks, spend_krw, revenue_krw, conversions
FROM `{UNI}.v_perf_unified_gender` WHERE date IS NOT NULL AND NOT IFNULL(is_excluded,FALSE)
"""

# ── 2) 커버리지 스냅샷 (정직성 배너 소스) ─────────────────────────────────
BUILD_COVERAGE = f"""
CREATE OR REPLACE TABLE `{MART}.mart_coverage` AS
SELECT
  platform,
  COUNT(*)                       AS rows_n,
  MIN(date)                      AS first_date,
  MAX(date)                      AS last_date,
  COUNT(DISTINCT date)           AS days_n,
  DATE_DIFF(MAX(date), MIN(date), DAY) + 1 AS span_days,
  COUNT(DISTINCT advertiser_id)  AS advertisers_n,
  COUNT(DISTINCT campaign_id)    AS campaigns_n,
  COUNTIF(brand_name IS NOT NULL) > 0 AS has_brand,
  COUNTIF(conversions IS NOT NULL) > 0 AS has_conversions,
  CURRENT_TIMESTAMP()            AS _built_at
FROM `{MART}.report_campaign_performance`
GROUP BY platform
"""

def run(label, sql):
    job = client.query(sql)
    job.result()
    print(f"  [OK] {label}")

if __name__ == "__main__":
    print("report-mart-builder: raw(READ) -> report_mart")
    run("report_campaign_performance", BUILD_PERFORMANCE)
    run("report_segments", BUILD_SEGMENTS)
    run("mart_coverage", BUILD_COVERAGE)
    # summary
    for r in client.query(f"SELECT platform, rows_n, first_date, last_date, days_n, advertisers_n, campaigns_n FROM `{MART}.mart_coverage` ORDER BY rows_n DESC").result():
        print(f"  {r.platform:8s} rows={r.rows_n:>9,} {r.first_date}~{r.last_date} ({r.days_n}d) adv={r.advertisers_n} camp={r.campaigns_n}")
