# INNOCEAN Report

Phase별 마케팅 성과 리포트 (AI / Media Mix / Daily / Phase) 솔루션.

🔗 **Production:** https://innocean-report-291757702623.asia-northeast3.run.app

---

## 빠른 시작 (인수인계용)

### 1. 로컬에서 보기

별도 빌드 도구 없음 — `index.html`을 브라우저로 열면 됩니다.

```bash
git clone https://github.com/InnoceanAX/AX-innocean-Report.git
cd AX-innocean-Report
open index.html        # macOS
# 또는 python3 -m http.server 8000 후 http://localhost:8000
```

### 2. Cloud Run 배포

GCP 프로젝트: `innocean-perf-apac-kr` (291757702623), 리전: `asia-northeast3`

```bash
gcloud run deploy innocean-report \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --port 8080 \
  --quiet
```

배포는 `Dockerfile`(nginx:alpine) + `nginx.conf`(port 8080, Cache-Control: no-store)로 처리됩니다.

### 3. 배포 후 검증

```bash
URL="https://innocean-report-291757702623.asia-northeast3.run.app"
curl -sI "$URL/" | grep -i "cache-control\|content-length"
# cache-control: no-store 확인 필수
```

---

## 문서

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 절대 규칙, 디자인 토큰, 라우팅
- [docs/FEATURES.md](docs/FEATURES.md) — 페이지별 기능 명세, AI 비서 패턴, 차트 빌더
- [CHANGELOG.md](CHANGELOG.md) — 변경 이력

---

## 아키텍처 원칙 (절대 규칙)

- **단일 HTML 파일** (`index.html`) — 모든 CSS/JS 인라인
- 외부 의존: **Chart.js + Pretendard 폰트 CDN만** 허용
- **vanilla JS** — 프레임워크 사용 금지
- **rounded-none** — `border-radius: 0`
- CSS 변수:
  - `--ind: #4F46E5` (키컬러)
  - `--ind2: #4338CA`
  - `--bdr: #E5E7EB`
  - `--ts: #555` / `--tm: #767676`
- 디자인 기준: INNOCEAN Brand Safety DOM 스펙. `adshub` 디자인 직접 사용 금지

## 페이지 구성

- **Daily 리포트** (기존) — 데일리 성과 종합. 매체별 성과 분석 테이블 포함
- **Phase 리포트** (신규) — 캠페인 Phase별 trend + radar 차트
- **AI 리포트** — AI 분석 채팅 사이드바 + Summary 차트

## 디멘션 / 인덱스 카탈로그

`window.DIM_CATALOG` / `window.IDX_CATALOG`는 BigQuery `0402_*_dm` 스키마 (특히 `campaign_performance`, `campaign_index`, `creative_index`) 컬럼을 직접 매핑합니다.

- 디멘션 12종: media, campaign, campaign_id, brand_name, advertiser_standardized, country, phase, creative, creative_type, date, year, month
- 인덱스 카테고리: 예산/비용 · 노출/도달 · 조회/영상(구간별) · 클릭/인터랙션(링크 클릭 포함) · 전환 · 인덱스(목표 대비 달성률)

새 인덱스 추가 시 반드시 BigQuery 데이터정의서의 실 컬럼명(`col` 필드)을 사용하세요.

## 작업 흐름

1. 로컬에서 `index.html` 수정
2. 따옴표 이스케이프 보존 검증
3. `git add . && git commit -m "..."` → `git push origin main`
4. Cloud Run 배포 (위 명령)
5. `curl`로 서버에서 핵심 토큰 검증
6. CEO에게 URL + 검증 결과 + Ctrl+Shift+R 안내

## CEO 1:1 채널
- 모든 피드백·승인은 채팅 채널을 통해 전달됨
- 변경 후 보고 시: URL + 변경 요약 + ALL PASSED 필수

## 알아두기
- AdsHub 기반 솔루션 — BigQuery 데이터정의서 0402_dm 시트 기준
- Daily = 기존 리포트 영역 / Phase = 신규 영역 (CEO 2026-06-08 확인)
- 매체 옵션은 4개로 유지 (Meta/Google/카카오/네이버). AdsHub 6세분화는 데이터 연동 단계에서 결정
- `Cache-Control: no-store` 항상 유지

## 운영
- 배포 권한: GCP SA `perf-data-analyst@innocean-perf-apac-kr.iam.gserviceaccount.com`
- INNOCEAN 내부 솔루션. 외부 공개 금지
