# Changelog

원칙: 사용자(CEO)에게 영향이 있는 변경만 기재. 코드 정리/리팩터는 git 커밋 메시지로만.

## 2026-06-08 — Cycle C UI overhaul
- **디멘션·인덱스 토글이 실제 화면에 반영됨**: 인덱스 추가/제거 시 달성률 카드·매체 테이블 컬럼·Phase 차트 시리즈가 즉시 변경 (mock 데이터)
- **AI 채팅 "관련 질문" 제거** (Report) — 사이드바 추천 질문 chips는 유지
- **지표 라벨 명확화** — 22개 인덱스 라벨을 비전문가도 이해 가능하도록 변경:
  - `1Q 조회수` → `영상 25% 시청수`, `VTR 25%` → `25% 시청 완료율` 등
  - `CPV` → `조회 1회당 비용 (CPV)`, `CPC` → `클릭 1회당 비용 (CPC)`, `CPM` → `노출 1,000회당 비용 (CPM)`
  - `ThruPlay` → `완전 시청 (ThruPlay)`
- **지표 (?) 툴팁** — 모든 지표 pill에 hover 설명 (40개 항목)
- **차트 강화**: Chart.js 단위 인식 툴팁 + PNG 다운로드 + 차트↔표 전환 토글
- **테이블 강화**: 실시간 검색 + 컬럼 정렬 (asc/desc 화살표) + CSV 다운로드 (Excel 호환 BOM)
- **북마크/리셋**: 각 디멘션·인덱스 패널에 기본값 리셋 + 그룹별 일괄 선택 + localStorage 북마크 저장/불러오기/삭제
- **다크 모드 토글** (헤더, localStorage 유지)
- **카드 접기/펴기** chevron (`.chart-card` / `.form-section`)
- **키보드 ←/→** 페이지 네비게이션 (AI / MM / Daily / Phase)

## 2026-06-08
- **AdsHub 기반 7-item Report UI overhaul**:
  - AI 감지 아이콘 `🤖` → `✦` (sparkles). 규칙 기반 `⚠`는 유지
  - 메인 페이지 AI 리포트 아이콘도 `✦`로 통일
  - AI 채팅 영역 확장: 추천 질문 chips(sqchips) + 응답 그라데이션 + Benchmark AI와 디자인 통일
  - 매체 선택: `<select multiple>` → 체크박스 다중선택 드롭다운 (`mc-wrap`, 전체 선택/해제 포함)
  - Daily / Phase 페이지에 디멘션·인덱스 동적 토글 패널 4곳 추가 (`di-panel`)
  - BigQuery `0402_dm` 스키마 기반 카탈로그 재정의:
    - 디멘션 12개 (media · campaign · brand_name · advertiser_standardized · country · phase · creative · creative_type · date · year · month · campaign_id)
    - 인덱스: 예산/노출·도달/조회·영상/클릭·인터랙션/전환/달성률 카테고리화
    - 구간별 조회수 전체 포함: video_play_25p/50p/75p/100p, first/third_quartile_views, video_thruplay
    - VTR 구간별: vtr_video_play_25p/50p/75p/100p, first/third_quartile_vtr
    - 링크 클릭: inline_link_clicks, ctr_inline_link_click, cpc_inline_link_click
- **Dockerfile + nginx.conf 정식 추가** — Cloud Run 직접 배포 가능

## 이전 작업
- 기본 Daily/Phase 페이지 구조 + Chart.js 시각화 정착
- AI 사이드바 + Summary 차트 구조
- CSS 변수 기반 디자인 시스템 적용

---
새 항목은 위쪽에 추가. 날짜 + 사용자 가시 변경 + 짧은 요약.
