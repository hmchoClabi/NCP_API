# T01 — 디자인 토큰 도입과 CSS 레이어 통합

> 선행: T00 완료. `docs/redesign/current-map.md` 9절(프런트엔드 자산 지도)을 참고하세요.
> 기준: `docs/redesign/01-design-system.md` 2·3절.

## 현행 반영 (T00 결과, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **경로**: CSS·JS·아이콘·폰트는 `webapp/static/`, 템플릿은 `webapp/templates/`입니다. 본문의 `static/…`, `templates/…`는 모두 `webapp/` 아래로 읽습니다.
  CSS 로드 위치는 `webapp/templates/base.html:9–14`.
- **헬퍼는 새로 만들지 말고 기존 `webapp/presentation.py`에서 시작**합니다: `format_kst`(:15), `format_duration`(:35), `format_status`(:58, Jinja 이름 `status_label`), `inclusive_end`(:66),
  그리고 T00B-9에서 추가한 `status_tone`. 본문의 `fmt_*`·`status_badge`는 이 함수들을 확장·개명하는 방식으로 구현하고(기존 Jinja 이름은 별칭으로 유지), 같은 일을 하는 두 번째 카탈로그를 만들지 않습니다.
  보고서 렌더러와 매핑을 공유하는 방법은 01-design-system.md 5.2 끝 문단을 따릅니다.
- 상태는 작업(`report_jobs`)과 보고서(`report_runs`) 두 축이며 `PENDING`은 없습니다(AGENTS.md 8절, 01-design-system.md 5.2).
- **구 CSS 파일 삭제 유보**: 로컬 산출물 HTML 74개에서는 `/static/` 참조가 0개였지만 운영 PVC는 확인하지 못했습니다(current-map 7.3).
  이번 작업에서는 base 템플릿의 로드만 바꾸고 원본 5개 파일은 **삭제하지 않습니다.** 삭제는 운영 PVC 읽기 전용 점검 후 별도 작업입니다.
- **소요 시간**: `/portal` "실행 시간"은 정수 초로 변환되며(`webapp/repository.py:2280`) 정밀도가 손실됩니다. 밀리초 컬럼을 추가하지 말고 `started_at`/`completed_at`에서 계산합니다.
- **테마 사전 적용**: 인라인 스크립트는 T00B-2의 CSP와 충돌하지 않아야 합니다. 서버가 쿠키 값으로 `<html data-theme>`를 직접 출력하는 방식(스크립트 불필요)을 우선 검토하고,
  인라인 스크립트가 꼭 필요하면 CSP 해시(또는 nonce)에 포함합니다.
- `base.html`에는 이미 `menu_link` 매크로가 있습니다. 컴포넌트 매크로 파일을 만들 때 중복되지 않게 합니다.
- 미사용 셀렉터 후보는 `portal.css`의 `.flash` 계열뿐입니다. `status`·`tab`·`toast`처럼 JS가 동적으로 붙이는 클래스는 정적 검색만으로 지우지 않습니다.
  `customer_detail.html`, `schedules.html`에도 인라인 JS가 있으니 함께 검색합니다.
- `ux.css`의 `!important`(:17–18, reduced-motion)는 접근성 목적입니다. 병합 후에도 같은 우선순위가 유지되는지 확인합니다.
- 시각 회귀 캡처 폭에 **1280px**을 포함합니다(375 / 768 / 1280 / 1440).
- 보고서 본문(Python 렌더러)은 범위가 아닙니다.

## 목표
`portal.css` + `automation.css` + `notifications.css` + `report_settings.css` + `ux.css`(덮어쓰기 패치)로
흩어진 스타일을 **토큰 기반 단일 진입점 `webapp/static/build/app.{build_id}.css`** 로 통합합니다.
화면 모양은 거의 그대로 유지하되(의도된 변경만 허용), 이후 작업이 패치 누적 없이 진행될 수 있게 합니다.

## 범위
- 포함: CSS 파일 재구성, 토큰 도입, base 템플릿의 CSS 로드 교체, 다크 모드 토큰과 테마 토글, 자체 호스팅 폰트, 공통 상태 배지·포맷 헬퍼.
- 제외: 레이아웃 구조 변경(T02), 화면 구성 변경(T03 이후), 보고서 본문(Python 렌더러, T08), 원본 CSS 파일 삭제(운영 PVC 확인 후 별도).

## 작업 지시

1. `webapp/static/css/` 아래에 01-design-system.md 2절 구조로 파일을 만듭니다.
   `00-tokens.css`는 3절 토큰을 **그대로** 옮깁니다.
2. 기존 5개 CSS 파일의 규칙을 하나씩 옮기면서
   - hex 색상·px 간격을 가장 가까운 토큰으로 치환 (`#64748b`/`#5b6a7f` → `var(--text-muted)`, `#1769e0` → `var(--accent)` 등)
   - 같은 셀렉터의 중복 규칙과 `ux.css`의 덮어쓰기를 **원래 규칙에 병합**
   - `!important` 제거 (visually-hidden 제외)
   - 1000px/720px 중복 미디어쿼리를 레이어별로 한 곳에 모으기 (T02에서 기준 폭을 바꿀 것이므로 지금은 값 유지)
   - 사용되지 않는 셀렉터(T00 9절 후보)는 템플릿 전체 검색으로 확인 후 삭제
3. `01-design-system.md` 2절의 이어 붙이기 스크립트로 `webapp/static/build/app.{build_id}.css`를 생성하고, base 템플릿의 기존 `<link>` 5개를 이 파일 `<link>` 하나로 교체합니다.
   원본 5개 파일은 **이번 작업에서 지우지 않고** 템플릿 로드만 제거합니다(운영 PVC 산출물의 `/static/` 참조 미확인, current-map 7.3).
4. **상태 배지 헬퍼** `status_badge(code, kind=None)` 를 기존 `format_status`(Jinja `status_label`)·`status_tone`을 확장해 한 곳에 구현하고(위 현행 반영 절, Jinja 전역 등록),
   01-design-system.md 5.2 표의 매핑을 넣습니다. 템플릿에서 `<span class="status ...">CODE</span>` 형태로
   상태를 직접 찍는 곳을 **모두** 이 헬퍼로 교체합니다.
   - 특히 `/history`에서 `PARTIAL_SUCCESS`가 `.status.ok`로 나오는 문제, 대시보드 "정보" 등급이 `.status.pending`인 문제가 해소되어야 합니다.
   - `/portal`의 `ACTIVE`, `SUCCESS`, `PARTIAL_SUCCESS`도 한국어 라벨로.
5. **포맷 헬퍼** `fmt_dt`, `fmt_date`, `fmt_period`, `fmt_ago`, `fmt_duration`, `fmt_krw`, `fmt_bytes`, `fmt_pct`를 기존 `format_kst`·`format_duration`·`inclusive_end`를 확장해 구현·등록하고,
   앱 화면(보고서 본문 제외)의 일시·기간·금액·용량 출력부를 교체합니다. `/portal` "실행 시간" 열은 시작·종료 시각에서 계산한 값을 `fmt_duration`에 넘깁니다
   (밀리초 컬럼 추가 금지, 위 현행 반영 절).
6. **아이콘**: 사용 아이콘(check, alert-triangle, x-circle, clock, loader, dot, archive, pause, alert-octagon, info, chevron, more-horizontal,
   search, bell, menu, external-link, download, printer, refresh, copy, hourglass, ban, key, lock, mail)과 메뉴용(layout-dashboard, siren, building, calendar-clock, sliders, file-text,
   history, users, hard-drive, panel-left-close, panel-left-open)을 SVG 스프라이트 `webapp/static/icons.svg`로 자체 호스팅.
   매크로 `icon(name, label=None)` — label 없으면 `aria-hidden="true"`.
7. **폰트**: Pretendard Variable woff2를 `webapp/static/fonts/`에 추가(라이선스 OFL 확인), `@font-face` + `font-display: swap`. 파일 다운로드는 네트워크가 필요하므로 사용자가 받아 넣을 위치·파일명을 안내합니다.
8. **다크 모드**: `light-dark()` 토큰이 시스템 설정을 따르게 하고, 사용자 메뉴에 `시스템 / 라이트 / 다크` 토글을 추가.
   선택값은 쿠키(서버가 첫 렌더에 `<html data-theme>` 출력, 깜빡임 방지) 우선, 보조로 `localStorage`(try/catch). 인라인 스크립트를 쓰면 CSP 해시에 포함(위 현행 반영 절).
9. 사이드바는 양 모드에서 `--nav-*` 토큰(어두운 남색)을 유지합니다.

## 완료 조건
- [ ] 템플릿이 로드하는 CSS `<link>`가 생성된 `app.{build_id}.css` 하나 (`grep -r "portal.css\|ux.css" webapp/templates/` 결과 0). 원본 CSS 파일은 남아 있음
- [ ] 컴포넌트·레이아웃 CSS 안에 hex 색상 직접 사용 0건 (`00-tokens.css` 제외) — 확인 명령과 결과 첨부
- [ ] `!important` 사용이 visually-hidden 1곳뿐
- [ ] 템플릿에서 상태 코드 문자열 직접 출력 0건, 모두 `status_badge` 경유. 상태 매핑 정의는 한 곳뿐(중복 카탈로그 0)
- [ ] 라이트/다크 전환 시 전 화면에서 대비 4.5:1 유지 (자동 점검 스크립트 또는 수동 표 첨부)
- [ ] 변경 전후 주요 화면 8개(대시보드·민간 고객·고객 상세·일정·보고서 보관함·이력·계정·데이터 정리)를 1440px에서 비교해 **의도치 않은 시각 차이 없음**
      (의도된 변경: 글꼴 Pretendard, `--text-muted` #5b6a7f→#4f5d72, 상태 배지 아이콘·한국어 라벨, 포맷 헬퍼 적용 문구. 그 외는 픽셀 비교 허용 오차 0.5% 이내)
- [ ] build-46에서 개선된 항목(00-context.md 8절)이 하나도 퇴행하지 않음

## 검증
- 시각 회귀: Playwright로 위 8개 화면을 375/768/1280/1440px, 라이트/다크로 캡처하는 스크립트 `tests/visual/capture.py`(또는 .ts)를 추가하고 전후 결과를 PR에 첨부.
- 상태 헬퍼 단위 테스트: 매핑 표 전 코드 + 알 수 없는 코드.
- 포맷 헬퍼 단위 테스트: 경계값(0ms, 999ms, 59.9초, 자정 걸친 기간, 음수 금액 등).
