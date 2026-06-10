# INNOCEAN Report Solution — 전용 데이터 마트 + 읽기 API

리포트 솔루션 **전용**(격리) 데이터 계층 + 백엔드. 설계 근거: [`../08_REPORT_CONSTRUCTION_PLAN.md`](../08_REPORT_CONSTRUCTION_PLAN.md)

## 격리 원칙
- 리포트는 **`report_mart` 데이터셋만** 사용. `apac_kr_raw`(수집AI 소유)는 **읽기 전용 소스** — ETL이 읽기만, 절대 쓰지 않음.
- **API SA**(`report-api-reader`)는 `report_mart` READ 만. raw 접근권 없음 → 격리를 권한으로 강제.

## 구성
```
report-solution/
├── etl/build_mart.py     # raw(READ) -> report_mart. 멱등(CREATE OR REPLACE). 매일 03:30 KST.
├── api/main.py           # FastAPI. report_mart 만 읽음. /coverage /catalog /query /targets
├── api/Dockerfile        # Cloud Run 배포용
└── api/requirements.txt
```

## 현재 적재 상태 (Phase 1)
`report_mart.report_campaign_performance` — 일×플랫폼×캠페인 grain, 94만 행
| platform | rows | 기간 |
|----------|------|------|
| meta | 791,539 | 2023-06-24 ~ 2026-06-08 |
| dv360 | 131,491 | 2024-07-01 ~ 2026-06-08 |
| tiktok | 19,075 | 2024-01-01 ~ 2026-06-08 |

`report_mart.mart_coverage` — 플랫폼별 신선도/공백 스냅샷 (정직성 배너 소스)

### 알려진 Phase 1 한계 (정직성)
- **spend 는 현지통화 그대로** + `currency`. `costs_krw/usd` 는 **FX 확정 후** 채움 → 그 전엔 **통화 혼합 합산 주의**(통화 디멘션으로 분리 권장).
- Meta `conversions` 스칼라는 비어있음(전환은 `actions` JSON 내부) → 추출은 다음 반복.
- 미적재: Google Ads / SA360 / CM360 / GA4 / Naver / Kakao → ETL 다음 반복에서 정규화 추가.

## ETL 실행 (수동)
```bash
cd etl
python build_mart.py /path/to/sa-key.json
```

## ETL 자동화 (Cloud Run Job + Scheduler)
```bash
# 빌드 & 배포 (빌더 SA = raw READ + report_mart WRITE)
gcloud run jobs deploy report-mart-builder --source ./etl --region asia-northeast3 \
  --service-account report-mart-builder@innocean-perf-apac-kr.iam.gserviceaccount.com
# 매일 03:30 KST 스케줄
gcloud scheduler jobs create http report-mart-daily --schedule "30 3 * * *" \
  --time-zone "Asia/Seoul" --uri ".../jobs/report-mart-builder:run" --http-method POST
```

## API 로컬 실행
```bash
cd api
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
uvicorn main:app --reload --port 8080
# http://localhost:8080/api/coverage
```

## API 배포 (Cloud Run, report-api-reader SA)
```bash
gcloud run deploy innocean-report-api --source ./api --region asia-northeast3 \
  --service-account report-api-reader@innocean-perf-apac-kr.iam.gserviceaccount.com \
  --allow-unauthenticated --port 8080
```

## 프론트 연결
`index.html` 에 `window.REPORT_API_BASE = "<API URL>"` 설정 시 실데이터 모드. 미설정 시 mock 유지(폴백).
