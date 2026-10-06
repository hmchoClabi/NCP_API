# T01 — 디자인 토큰 도입과 CSS 레이어 통합

> 선행: T00 완료. `docs/redesign/current-map.md` 9절(프런트엔드 자산 지도)을 참고하세요.
> 기준: `docs/redesign/01-design-system.md` 2·3절.

## 목표
`portal.css` + `automation.css` + `notifications.css` + `report_settings.css` + `ux.css`(덮어쓰기 패치)로
흩어진 스타일을 **토큰 기반 단일 진입점 `static/css/app.css`** 로 통합합니다.
화면 모양은 거의 그대로 유지하되(의도된 변경만 허용), 이후 작업이 패치 누적 없이 진행될 수 있게 합니다.

## 범위
- 포함: CSS 파일 재구성, 토큰 도입, base 템플릿의 CSS 로드 교체, 다크 모드 토큰과 테마 토글, 자체 호스팅 폰트, 공통 상태 배지·포맷 헬퍼.
- 제외: 레이아웃 구조 변경(T02), 화면 구성 변경(T03 이후), 보고서 본문 템플릿(T08).

## 작업 지시

1. `static/css/` 아래에 01-design-system.md 2절 구조로 파일을 만듭니다.
   `00-tokens.css`는 3절 토큰을 **그대로** 옮깁니다.
2. 기존 5개 CSS 파일의 규칙을 하나씩 옮기면서
   - hex 색상·px 간격을 가장 가까운 토큰으로 치환 (`#64748b`/`#5b6a7f` → `var(--text-muted)`, `#1769e0` → `var(--accent)` 등)
   - 같은 셀렉터의 중복 규칙과 `ux.css`의 덮어쓰기를 **원래 규칙에 병합**
   - `!important` 제거 (visually-hidden 제외)
   - 1000px/720px 중복 미디어쿼리를 레이어별로 한 곳에 모으기 (T02에서 기준 폭을 바꿀 것이므로 지금은 값 유지)
   - 사용되지 않는 셀렉터(T00 9절 후보)는 템플릿 전체 검색으로 확인 후 삭제
3. `01-design-system.md` 2절의 이어 붙이기 스크립트로 `static/build/app.{build_id}.css`를 생성하고, base 템플릿의 기존 `<link>` 5개를 이 파일 `<link>` 하나로 교체합니다.
   원본 5개 파일을 지우기 **전에** T00 19번(과거 산출물의 `/static/` 참조) 결과를 확인하세요. 참조가 있으면 원본 파일은 남겨 두고 템플릿 로드만 제거합니다.
4. **상태 배지 헬퍼** `status_badge(code, kind=None)` 를 서버 측에 한 곳(예: `app/ui/status.py` + Jinja 전역 등록)에 구현하고,
   01-design-system.md 5.2 표의 매핑을 넣습니다. 템플릿에서 `<span class="status ...">CODE</span>` 형태로
   상태를 직접 찍는 곳을 **모두** 이 헬퍼로 교체합니다.
   - 특히 `/history`에서 `PARTIAL_SUCCESS`가 `.status.ok`로 나오는 문제, 대시보드 "정보" 등급이 `.status.pending`인 문제가 해소되어야 합니다.
   - `/portal`의 `ACTIVE`, `SUCCESS`, `PARTIAL_SUCCESS`도 한국어 라벨로.
5. **포맷 헬퍼** `fmt_dt`, `fmt_date`, `fmt_period`, `fmt_ago`, `fmt_duration`, `fmt_krw`, `fmt_bytes`, `fmt_pct`를 구현·등록하고,
   앱 화면(보고서 본문 제외)의 일시·기간·금액·용량 출력부를 교체합니다. `/portal` "실행 시간" 열은 `fmt_duration(ms)`로
   (원천 값이 초 단위 정수뿐이면 T00 결과에 따라 밀리초 저장 여부를 계획에 적고 승인받으세요).
6. **아이콘**: 사용 아이콘(check, alert-triangle, x-circle, clock, loader, dot, archive, pause, alert-octagon, info, chevron, more-horizontal,
   search, bell, menu, external-link, download, printer, refresh, copy, hourglass)과 메뉴용(layout-dashboard, siren, building, calendar-clock, sliders, file-text,
   history, users, hard-drive, panel-left-close, panel-left-open)을 SVG 스프라이트 `static/icons.svg`로 자체 호스팅.
   매크로 `icon(name, label=None)` — label 없으면 `aria-hidden="true"`.
7. **폰트**: Pretendard Variable woff2를 `static/fonts/`에 추가(라이선스 OFL 확인), `@font-face` + `font-display: swap`.
8. **다크 모드**: `light-dark()` 토큰이 시스템 설정을 따르게 하고, 사용자 메뉴에 `시스템 / 라이트 / 다크` 토글을 추가.
   선택값은 `localStorage`(try/catch) + 첫 페인트 전 `<html data-theme>` 적용 인라인 스크립트(깜빡임 방지).
9. 사이드바는 양 모드에서 `--nav-*` 토큰(어두운 남색)을 유지합니다.

## 완료 조건
- [ ] 템플릿이 로드하는 CSS `<link>`가 생성된 `app.{build_id}.css` 하나 (`grep -r "portal.css\|ux.css" templates/` 결과 0)
- [ ] 컴포넌트·레이아웃 CSS 안에 hex 색상 직접 사용 0건 (`00-tokens.css` 제외) — 확인 명령과 결과 첨부
- [ ] `!important` 사용이 visually-hidden 1곳뿐
- [ ] 템플릿에서 상태 코드 문자열 직접 출력 0건, 모두 `status_badge` 경유
- [ ] 라이트/다크 전환 시 전 화면에서 대비 4.5:1 유지 (자동 점검 스크립트 또는 수동 표 첨부)
- [ ] 변경 전후 주요 화면 8개(대시보드·민간 고객·고객 상세·일정·보고서 보관함·이력·계정·데이터 정리)를 1440px에서 비교해 **의도치 않은 시각 차이 없음**
      (의도된 변경: 글꼴 Pretendard, `--text-muted` #5b6a7f→#4f5d72, 상태 배지 아이콘·한국어 라벨, 포맷 헬퍼 적용 문구. 그 외는 픽셀 비교 허용 오차 0.5% 이내)
- [ ] build-46에서 개선된 항목(00-context.md 8절)이 하나도 퇴행하지 않음

## 검증
- 시각 회귀: Playwright로 위 8개 화면을 375/768/1440px, 라이트/다크로 캡처하는 스크립트 `tests/visual/capture.py`(또는 .ts)를 추가하고 전후 결과를 PR에 첨부.
- 상태 헬퍼 단위 테스트: 매핑 표 전 코드 + 알 수 없는 코드.
- 포맷 헬퍼 단위 테스트: 경계값(0ms, 999ms, 59.9초, 자정 걸친 기간, 음수 금액 등).
