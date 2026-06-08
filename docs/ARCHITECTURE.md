# ARCHITECTURE — INNOCEAN Report

## 절대 규칙 (변경 불가)

1. **단일 HTML 파일**: 모든 CSS / JS 는 `index.html` 안에 인라인. 별도 빌드 도구 없음.
2. **외부 의존**: Chart.js (CDN) + Pretendard 폰트 (CDN) **만** 허용.
3. **vanilla JS**: 프레임워크 / jQuery 일체 금지.
4. **rounded-none** (chip / pill 예외).
5. **Cache-Control: no-store**: nginx 설정으로 항상 강제.
6. **Brand Safety DOM 기준**: 디자인 baseline. 추정 금지.
7. **adshub 디자인 절대 사용 금지**.
8. **이모지 사용 금지** — 모든 아이콘은 inline SVG (line / stroke 기반).

## 디자인 토큰

```css
:root{
  --ind:#4F46E5; --ind2:#4338CA;
  --bg:#fff; --bg-soft:#FAFAFA; --bg-soft2:#F3F4F6;
  --text:#000; --text2:#374151; --text3:#555; --text4:#767676;
  --border-c:#E5E7EB;
  --card-bg:#fff; --input-bg:#fff; --row-hover:#F9F9FF;
  --bdr:#E5E7EB; --ts:#555; --tm:#767676;
}
body.dark{
  --bg:#0F172A; --bg-soft:#111827; --bg-soft2:#1F2937;
  --text:#F9FAFB; --text2:#E5E7EB; --text3:#CBD5E1; --text4:#9CA3AF;
  --border-c:#374151; --card-bg:#1E293B; --input-bg:#0F172A; --row-hover:#1E293B;
}
```

## Chrome

| 영역 | 위치 | 높이 | 내용 |
|---|---|---|---|
| Header | fixed top | 70px | INNOCEAN 로고 + 세로바 + `REPORT` 라벨 + nav 탭 4개 |
| Subheader | fixed top+70 | 40px | 좌 `INNOCEAN AI SOLUTION` / 우 `Vol. 2026` (border-bottom 2px solid #000) |
| Footer | document end | 80px | 좌 `\| INNOCEAN` / 우 copyright |

## 페이지 라우팅

- nav 탭 4개: `ai-assistant` / `media-mix` / `daily-kpi` / `phase-kpi`
- `showPage(id)` — `.page` 클래스 토글
- URL hash 라우팅 미적용 (Phase 2 예정)

## 컴포넌트 패턴

### 카드

```css
.card{ border:2px solid var(--bdr); border-radius:0; padding:24px; }
.card:hover{ border-color:#000; }
```

### 디멘션/지표 바 (`.di-panel`)

```css
.di-pill{
  display:inline-flex; align-items:center; gap:4px;
  padding:5px 10px;
  background:#fff; border:1px solid var(--bdr);
  font-size:12px; color:#374151;
  border-radius:14px; cursor:pointer;
}
.di-pill.on{
  background:#1F2937; color:#fff;
  border-color:#1F2937; font-weight:600;
}
.di-addbtn{
  background:#fff; border:1px dashed #9CA3AF;
  padding:5px 10px; font-size:12px; color:#555;
  border-radius:14px;
}
```

### 차트 빌더 모달 (`.cb-modal`)

- 차트 이름 입력
- 차트 타입 카드 4개 (`.cb-type-card`) — 선/막대/도넛/레이더 (이모지 금지, SVG 아이콘)
- X축 디멘션 1개 (`.cb-pills` `.cb-pill` — `.di-pill` 와 동일 스타일)
- Y축 지표 N개 (동일 패턴)
- 자동 추천: 지표가 % 단위 포함 시 line, 아니면 bar

## SVG 아이콘 규약

- viewBox `0 0 24 24`.
- `fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round`.
- 다크 모드 자동 대응 (color:var(--text) on dark).

## 차트 (Chart.js 4.4)

- 4 types: `line` / `bar` / `doughnut` / `radar`.
- `responsive:true`, `maintainAspectRatio:false`.
- 색 팔레트: `var(--ind)`, `#1F2937`, `#9CA3AF`, RGBA 0.1~0.2.

## 폴더 구조

```
AX-innocean-Report/
├── index.html
├── Dockerfile
├── nginx.conf
├── README.md
├── CHANGELOG.md
└── docs/
    ├── ARCHITECTURE.md
    └── FEATURES.md
```

## 배포

```bash
gcloud run deploy innocean-report --source . --region asia-northeast3 --allow-unauthenticated --port 8080 --quiet
```

배포 후 검증 — `Cache-Control: no-store` 응답 헤더 + 키워드 grep.
