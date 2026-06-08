# Changelog

원칙: 사용자(CEO)에게 영향이 있는 변경만 기재. 코드 정리/리팩터는 git 커밋 메시지로만.

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
