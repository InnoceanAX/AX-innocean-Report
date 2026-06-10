# 전용 SA 격리 — 관리자 핸드오프 (1회)

리포트 API/ETL이 지금 공용 `perf-data-analyst`(BQ Admin급 + 배포권한)로 돌아갑니다.
완전 격리·최소권한·감사명료를 위해 **전용 SA**가 필요한데, SA 생성은 `iam.serviceAccounts.create`
권한이 있어야 합니다(perf-data-analyst엔 없음). **아래 1회 작업만 관리자가 해주시면, 나머지(마트 읽기권한 부여 + 재배포 + 검증)는 자동 처리됩니다.**

## 관리자 작업 (택1)

### A. gcloud
```bash
PROJ=innocean-perf-apac-kr
# 1) API 전용 SA (읽기 전용)
gcloud iam service-accounts create report-api-reader --project $PROJ \
  --display-name "INNOCEAN Report API (read-only mart)"
# 2) 쿼리 잡 실행 권한만 (데이터 접근 X — 데이터는 마트 ACL로 별도 부여)
gcloud projects add-iam-policy-binding $PROJ \
  --member "serviceAccount:report-api-reader@$PROJ.iam.gserviceaccount.com" \
  --role roles/bigquery.jobUser

# (선택) ETL 빌더 전용 SA — raw 읽기 + 마트 쓰기 분리하려면
gcloud iam service-accounts create report-mart-builder --project $PROJ \
  --display-name "INNOCEAN Report ETL builder"
gcloud projects add-iam-policy-binding $PROJ \
  --member "serviceAccount:report-mart-builder@$PROJ.iam.gserviceaccount.com" \
  --role roles/bigquery.jobUser
#   + apac_kr_unified(또는 raw) READ 는 데이터셋 ACL로 부여(우리가 처리 가능) 또는 dataViewer
```

### B. Console
IAM & Admin → Service Accounts → CREATE → 이름 `report-api-reader` → 역할 `BigQuery Job User`.

## 그 다음 (우리가 자동 실행)
```bash
cd report-solution/deploy
python finalize_sa.py <SA_KEY.json> report-api-reader@innocean-perf-apac-kr.iam.gserviceaccount.com \
  [report-mart-builder@innocean-perf-apac-kr.iam.gserviceaccount.com]
```
→ ① report_mart 에 전용 SA READER ACL 부여 ② API(+Job) 런타임 SA 교체 재배포 ③ 동작 검증.
완료 후 리포트는 **마트 읽기 권한만 가진 전용 신분증**으로 동작 → perf-data-analyst 의존 제거.

## 검증 포인트
- API `/` 응답 정상 + `/api/coverage` 정상(전용 SA로 마트 읽기 성공)
- BQ 잡 로그 principal = `report-api-reader@...` (감사 명료)
- 전용 SA로는 `apac_kr_raw` 쿼리 시 권한오류(= 격리 성공)
