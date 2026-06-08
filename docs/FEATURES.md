# FEATURES — INNOCEAN Report

## 페이지 4개

| 페이지 | 위치 | 설명 |
|---|---|---|
| AI 비서 | `#ai-assistant` | 자연어 입력 → 차트 생성 / 디멘션 추가 등 |
| Media Mix | `#media-mix` | 매체 KPI 트리 (매체 → 광고상품 계층) |
| Daily KPI | `#daily-kpi` | 일별 성과 + 차트 빌더 |
| Phase KPI | `#phase-kpi` | Phase 단위 성과 + 차트 빌더 |

---

## 1. AI 비서

### 입력 패턴 (rule-based, LLM 미연동)

| 의도 | 키워드 | 동작 |
|---|---|---|
| 차트 추가 | "차트 추가 / 그려줘 / 만들어줘" + 디멘션 + 지표 | `store[page].push(...)` + 자동 차트 이름 생성 |
| 디멘션 추가 | "디멘션 / 구분 / 축" + "추가 / 넣어" | `di-panel` chip 추가 |
| 지표 추가 | "지표 / 인덱스 / KPI" + "추가" | 지표 chip 추가 |
| 차트 변경 | "마지막 차트 ~로 바꿔줘" | 직전 차트의 type / dim / idx 교체 |
| 페이지 이동 | "Phase 보여줘 / Daily" | `showPage(id)` |
| 다크 모드 | "다크 / 라이트 모드" | `body.dark` 토글 |
| PNG 저장 | "차트 PNG로 저장" | Chart.js canvas → Blob download |

### 자동 추론 규칙

- **차트 타입**: 사용자 명시 우선. 미명시 시 지표 단위 기반 — `%` 포함 → line, 정수/금액 → bar.
- **X축 디멘션**: type=bar/doughnut → `media`, type=line → `date`.
- **차트 이름**: `[디멘션 라벨] [지표 라벨1] [지표 라벨2] [모드]` 자동 표준화.

### 지원 디멘션 (10+)

- media (매체) / product (광고 상품) / date (일자) / campaign / placement / device / age / region 등.

### 지원 지표 (15+)

- imp (노출수), clk (클릭수), ctr (클릭률, %), cpc, cpm, spend (집행액), cv (전환수), roas (%), revenue, vtr (완료율, %), reach (도달수), play (조회수) 등.

---

## 2. Media Mix (매체-광고상품 KPI 트리)

### 구조

- `KPI_TREE` 배열 — 매체 4개 (Google / Meta / Naver / Kakao).
- 각 매체에 `products[]` — 광고 상품 (서치/디스플레이 등).
- 매체 단위 KPI 5개: imp / clk / ctr / cpm / cpc.
- 광고 상품 토글 (+/−), 동적 추가/삭제 가능.

### 인터랙션

| 액션 | 함수 |
|---|---|
| 매체 펼침/접힘 | `kpiToggleMedia(mid)` |
| 매체 값 변경 | `kpiSetMedia(mid, key, val)` |
| 상품 값 변경 | `kpiSetProduct(mid, pid, key, val)` |
| 상품 추가 | `kpiAddProduct(mid)` |
| 상품 삭제 | `kpiDelProduct(mid, pid)` |
| 매체 추가 | `kpiAddMedia()` |
| 매체 삭제 | `kpiDelMedia(mid)` |

---

## 3. Daily KPI / Phase KPI

### 디멘션·지표 바 (`.di-panel`)

상단에 chip 형식으로 표시 / 추가 / 삭제.

- 디멘션 카탈로그에서 선택 (체크박스 다중 선택).
- 지표 카탈로그에서 선택.
- 선택된 chip 은 `.on` 상태 (배경 #1F2937 어두운 색 + 흰 글씨).
- 디멘션은 N단계 계층 트리로 표 1열에 표시.

### KPI 그리드

- 선택된 디멘션 × 지표 매트릭스를 카드 형태로 표시.
- 빈 상태: "지표를 추가해주세요".

### 차트 추가 모달 (`+ 차트 추가` 버튼)

1. **차트 이름** — 빈 칸 시 자동 생성 (`[디멘션] [지표] [모드]`).
2. **차트 타입** — 4 cards (선/막대/도넛/레이더, SVG 아이콘).
   - 지표 단위 기반 자동 추천 (`*-recommended` 클래스로 강조).
   - 사용자가 명시적으로 선택하면 `.on` 상태 (배경 검정 + 흰 글씨).
3. **X축 디멘션 (1개)** — chip 1개만 선택. 메인 `.di-pill` 와 동일 스타일.
4. **Y축 지표 (N개)** — chip 다중 선택.
5. **차트 생성** — `store[page].push({id, name, type, dim, idxs})` + 즉시 렌더.

### 차트 카드

- 우상단 메뉴 (이름 수정 / 타입 변경 / 디멘션 변경 / 지표 변경 / 삭제).
- Chart.js 4.4 캔버스.

---

## 디멘션·지표 chip 디자인 규약

메인 `.di-panel`, 차트 추가 모달 `.cb-pills` 모두 동일 패턴 적용.

```
선택됨 (.on): 배경 #1F2937 + 흰 글씨 + border 1px solid #1F2937 + border-radius 14px
미선택      : 배경 #fff + 회색 글씨 + border 1px solid var(--bdr) + border-radius 14px
hover       : border-color #000
추가 버튼    : 배경 #fff + 1px dashed #9CA3AF + "+ 선택"
```

---

## 차트 타입 4종 (모달 카드)

| 타입 | SVG 아이콘 | 추천 조건 |
|---|---|---|
| `line` | 꺾은선 + 데이터 점 | 지표가 % 단위 포함 |
| `bar` | 세로 막대 3개 | 정수/금액 지표 |
| `doughnut` | 원 + 안쪽 원 + 4 dividers | 구성비 분석 |
| `radar` | 오각형 2겹 + 십자축 | 다지표 비교 |

---

## 차트 범례 규칙 (CEO 2026-06-08 18:57)

- **항상 표시** — `legend.display: true` 고정. 데이터셋 1개여도 레이블 표시.
- **위치** — 기본 하단 중앙 (`position: 'bottom'`, `align: 'center'`).
  예외: 도넋(`doughnut`)만 우측 (`position: 'right'`) — 색-라벨 매핑이 직관적.
- **레이더** 역시 하단 표시.
- **패딩**: 10px (가독성).

## 차트 다크 모드 (CEO 2026-06-08 18:57)

- `applyChartDefaults()` 함수 — `body.dark` 여부에 따라 Chart.js 전역 설정 분기.
  - 글자: 라이트 `#374151` / 다크 `#E5E7EB`
  - borderColor: 라이트 `#E5E7EB` / 다크 `#374151`
  - tooltip: 라이트 검은 / 다크 진한 네이비
- `MutationObserver` — `body class` 변경 감지 → 활성 차트 모두 `update('none')`.
- 사용자가 테마 토글하면 차트 글자 색이 즉시 따라옴.

## 다크 모드

- 헤더 `theme-btn` 클릭 → `body.dark` 토글.
- 모든 컴포넌트가 `var(--*)` 토큰 사용 → 자동 전환.
- localStorage 저장 (Phase 2).

---

## PNG 다운로드

- 차트 카드의 다운로드 버튼 → `chart.toBase64Image()` → blob → download.

---

## Phase 2 예정

1. BigQuery 실데이터 연동 (현재 mock).
2. LLM AI 비서 (Gemini Flash) — rule-based → 자연어 이해.
3. PDF 보고서 내보내기.
4. URL hash 라우팅 + 페이지 상태 직렬화.
5. 권한 관리 (광고주별 view).
