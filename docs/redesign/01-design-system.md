# 01. 디자인 시스템 기준

> 모든 UI 작업은 이 문서를 기준으로 합니다. 값이 필요하면 여기서 가져오고, 없으면 토큰을 추가한 뒤 쓰세요.

## 1. 디자인 방향 (2026 운영·리포팅 SaaS 기준)

이 도구는 매일 아침 여러 고객의 상태를 훑고, 조치하고, 보고서를 꺼내 가는 **운영 도구**입니다.
화려함보다 **빠른 판단**이 목표입니다.

| 원칙 | 적용 방식 |
|---|---|
| **조치할 것 먼저** | 대시보드 첫 줄은 "지금 확인할 이슈". KPI는 그 다음. 정적 통계는 아래로. |
| **차분한 표면, 색은 상태에만** | 중립 회색 배경·흰 카드·얇은 테두리. 강조색(브랜드 블루)은 주요 버튼·링크·현재 위치에만. 빨강/주황/초록은 상태 표시에만. |
| **데이터 밀도는 높게, 위계는 분명하게** | 표·목록은 촘촘하게(행 높이 44–48px), 숫자는 `tabular-nums`, 보조 정보는 `--text-muted` 한 단계로만. |
| **신선도를 항상 표시** | 모든 집계 옆에 "기준 시각"과 "커버리지"(예: `10:30 기준 · 16/16 계정`)를 붙임. |
| **같은 패턴 반복** | 모든 목록 = 필터 바 + 표(모바일 카드) + 페이지네이션. 모든 상세 = 헤더 + 탭. 모든 파괴적 동작 = 위험 영역. |
| **맥락을 잃지 않기** | 행 상세는 가능하면 오른쪽 **사이드 시트**(`<dialog>`)로. 필터·탭 상태는 URL 쿼리스트링에 유지. |
| **다크 모드 기본 지원** | `light-dark()` 토큰. 사용자 토글(시스템/라이트/다크) + 저장. |
| **키보드 우선** | `⌘K`/`Ctrl+K` 명령 팔레트(고객·보고서·화면 이동), `/`로 목록 검색 포커스, `Esc`로 시트·대화상자 닫기. |

## 2. CSS 구조

```
static/css/
├── 00-tokens.css        @layer tokens
├── 10-base.css          @layer base        (reset, 타이포, 링크, 포커스, 스킵링크)
├── 20-layout.css        @layer layout      (앱 셸, 사이드바, 상단바, 페이지 그리드)
├── 30-components/       @layer components  (button, badge, card, table, form, tabs, sheet, toast …)
├── 40-pages/            @layer pages       (화면 전용 소량 규칙)
└── 90-utilities.css     @layer utilities   (visually-hidden, truncate, stack 등)
```

`@import` 체인은 렌더를 지연시키고 캐시 버스팅이 안 되므로 쓰지 않습니다. 대신 **서버 시작 시(또는 배포 이미지 빌드 시) 파일을 순서대로 이어 붙이는 짧은 스크립트**로
`static/build/app.{build_id}.css` 하나를 만들고, 템플릿은 이 파일만 `<link>`합니다(별도 프런트엔드 빌드 도구는 도입하지 않음).

```text
출력 첫 줄:  @layer tokens, base, layout, components, pages, utilities;
이어 붙이기: 00-tokens.css → @layer tokens { … }
             10-base.css → @layer base { … }
             20-layout.css → @layer layout { … }
             30-components/*.css (파일명 정렬) → @layer components { … }
             40-pages/*.css (파일명 정렬) → @layer pages { … }
             90-utilities.css → @layer utilities { … }
개발 모드: 요청 시 원본 파일 mtime이 바뀌었으면 다시 생성
```

- 기존 `portal.css`, `automation.css`, `notifications.css`, `report_settings.css`, `ux.css`의 규칙은
  위 구조로 **이동**하고 원본 파일은 삭제합니다. `!important`는 `utilities` 레이어의 `visually-hidden` 외에는 금지.
- 생성 파일명에 `build_id`가 들어가므로 캐시 버스팅이 자동으로 됩니다. JS는 현재처럼 `?v={{ build_id }}`.
- 보고서 본문(`/reports/{id}/content`)은 **자체 완결형 HTML**이어야 하므로 앱 CSS를 링크하지 않습니다.
  대신 같은 토큰 값을 보고서 템플릿 인라인 CSS에 복제합니다(`report-tokens.css`를 렌더 시 인라인).

## 3. 토큰

글자 조합은 모두 4.5:1 이상으로 검증했습니다. `--border-input`은 비텍스트 대비 3:1 이상(입력·체크박스·선택 상자 테두리용)이고,
`--border`·`--border-strong`은 카드·표 구분선 같은 **장식용**입니다(입력 테두리에 쓰지 마세요).

```css
/* 00-tokens.css */
:root {
  color-scheme: light dark;

  /* 표면 */
  --bg:          light-dark(#f6f8fb, #0b1220);
  --surface:     light-dark(#ffffff, #111a2b);
  --surface-2:   light-dark(#f1f5f9, #172338);   /* 표 헤더, 요약 타일, 입력 배경 */
  --border:      light-dark(#dfe6ee, #24324a);
  --border-strong: light-dark(#c7d2df, #33445f);
  --border-input: light-dark(#7d8ca1, #5d7090);   /* on surface 3.4 / 3.5 */

  /* 글자 */
  --text:        light-dark(#0b1733, #e6edf7);   /* on surface 17.7 / 14.8 */
  --text-muted:  light-dark(#4f5d72, #9fb0c8);   /* on surface 6.7 / 7.9 */
  --text-on-accent: light-dark(#ffffff, #0b1220);

  /* 강조 */
  --accent:      light-dark(#1769e0, #5aa2ff);   /* on surface 5.1 / 6.7 */
  --accent-soft: light-dark(#f0f6ff, #13284a);   /* accent 글자 4.7 / 5.6 */

  /* 상태: fg / bg  (모두 fg-on-bg 5.3:1 이상) */
  --ok-fg:      light-dark(#05704f, #5ee0aa);  --ok-bg:      light-dark(#e7f7f0, #0f2e24);
  --warn-fg:    light-dark(#9a4b00, #ffb55c);  --warn-bg:    light-dark(#fff3e2, #3a2610);
  --danger-fg:  light-dark(#b4232f, #ff8a94);  --danger-bg:  light-dark(#fdecee, #3b151a);
  --info-fg:    light-dark(#1b5fbf, #8cbcff);  --info-bg:    light-dark(#e8f1fe, #13284a);
  --neutral-fg: light-dark(#4f5d72, #a9b6c9);  --neutral-bg: light-dark(#eef2f6, #1c2738);

  /* 사이드바 (양 모드 공통 어두운 남색) */
  --nav-bg:      #0c2344;
  --nav-text:    #c6d4e9;   /* 10.5 */
  --nav-label:   #8aa4c6;   /* 6.1 */
  --nav-current-bg: rgb(23 105 224 / .28);
  --nav-current-bar: #6fb7ff;

  /* 타이포 */
  --font-sans: "Pretendard Variable", Pretendard, "Noto Sans KR", system-ui, sans-serif;
  --font-mono: ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
  --fs-xs: .75rem;   /* 12  보조 메타 */
  --fs-sm: .8125rem; /* 13  표 본문 */
  --fs-md: .9375rem; /* 15  기본 본문 */
  --fs-lg: 1.125rem; /* 18  패널 제목 */
  --fs-xl: 1.5rem;   /* 24  페이지 제목(모바일) */
  --fs-2xl: 1.875rem;/* 30  페이지 제목(데스크톱) */
  --fs-kpi: 2rem;    /* 32  KPI 숫자 */
  --lh-tight: 1.3; --lh-body: 1.6;

  /* 간격 (4px 기반) */
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 20px;
  --sp-6: 24px; --sp-8: 32px; --sp-10: 40px; --sp-12: 48px;

  /* 모양 */
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 14px; --radius-pill: 999px;
  --shadow-1: 0 1px 2px rgb(16 39 74 / .06);
  --shadow-2: 0 8px 24px rgb(16 39 74 / .10);

  /* 레이아웃 */
  --sidebar-w: 248px; --sidebar-rail-w: 64px; --topbar-h: 56px; --content-max: 1360px;

  /* 움직임 */
  --dur-fast: 120ms; --dur-base: 200ms; --ease: cubic-bezier(.2,.7,.2,1);

  /* z-index */
  --z-sticky: 10; --z-nav: 20; --z-sheet: 40; --z-toast: 60; --z-palette: 80;
}
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"]  { color-scheme: dark; }
@media (prefers-reduced-motion: reduce) { :root { --dur-fast: 0ms; --dur-base: 0ms; } }
```

글꼴은 Pretendard Variable woff2를 `static/fonts/`에 자체 호스팅하고 `font-display: swap`.
숫자 열·KPI·시각에는 `font-variant-numeric: tabular-nums;`

## 4. 레이아웃·반응형

| 폭 | 사이드바 | 상단바 | 본문 |
|---|---|---|---|
| ≥1280 | 펼침 248px (사용자가 레일로 접기 가능, 상태 저장) | 브레드크럼 · 검색(⌘K) · 알림 · 사용자 | 최대 1360px, 좌우 32px |
| 768–1279 | **아이콘 레일 64px** (호버/포커스 시 툴팁, 클릭으로 펼침 오버레이) | 동일 | 좌우 24px |
| <768 | 숨김 → 햄버거로 **드로어**(`<dialog>`) | 로고 · 현재 화면명 · 검색 아이콘 · 알림 | 좌우 16px |

- 컴포넌트 내부 배치는 **뷰포트 미디어쿼리 대신 컨테이너 쿼리**를 씁니다
  (`.panel { container-type: inline-size; }` → `@container (width < 560px) { … }`).
- KPI 영역은 벤토 그리드: `grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`.
- 페이지 헤더: 제목 + 설명(좌) / 주요 동작 1개 + 보조 동작(우). 좁아지면 세로로 쌓임.

## 5. 컴포넌트 명세

각 컴포넌트는 `templates/components/`에 Jinja 매크로(또는 해당 스택의 partial)로 만들고, 화면에서는 매크로만 호출합니다.

### 5.1 Button
- 변형: `primary`(강조색 채움) / `secondary`(surface-2 채움) / `ghost`(테두리 없음) / `danger`(danger-fg 테두리·글자, 채움 없음) / `danger-solid`(위험 영역의 최종 실행 버튼만)
- 크기: `md` 40px, `sm` 32px. 모바일에서 모든 버튼 최소 44px.
- 로딩 상태: `aria-busy="true"` + 스피너 + 비활성. 폼 이중 제출 방지.
- 한 화면(또는 한 패널)에 `primary`는 하나만.

### 5.2 StatusBadge — `status_badge(code, kind=None)`
아이콘 + 한국어 라벨 + 톤. 원 코드는 `title`과 `data-code`에만.
`kind`는 같은 코드가 다른 의미로 쓰일 때 구분하는 이름공간입니다(기본 `None` = 작업·고객 상태).
일정은 `enabled` 값을 `schedule_state(schedule) -> "ACTIVE" | "PAUSED"`로 바꾼 뒤 `status_badge(..., kind="schedule")`로 표시합니다.

| kind | 코드 | 라벨 | 톤 | 아이콘 |
|---|---|---|---|---|
| (기본) | `SUCCESS` | 정상 완료 | ok | check |
| | `PARTIAL_SUCCESS` | 부분 수집 | warn | alert-triangle |
| | `FAILED` / `ERROR` | 실패 | danger | x-circle |
| | `PENDING` / `QUEUED` | 대기 | neutral | clock |
| | `RUNNING` | 실행 중 | info | loader |
| | `WAITING_DATA` | 데이터 대기 | info | hourglass |
| | `ACTIVE` | 활성 | ok | dot |
| | `ONBOARDING` | 온보딩 중 | info | dot |
| | `OFFBOARDED` | 오프보딩됨 | neutral | archive |
| `schedule` | `ACTIVE` / `PAUSED` | 활성 / 일시 중지 | ok / neutral | dot / pause |
| `severity` | `CRITICAL` / `WARNING` / `INFO` | 위험 / 주의 / 정보 | danger / warn / info | alert-octagon / alert-triangle / info |
| `issue_state` | `OPEN` / `ACKNOWLEDGED` / `RESOLVED` / `STALE` / `MUTED` | 진행 중 / 확인함 / 해결됨 / 종료 미확인 / 음소거 | danger / info / ok / neutral / neutral | |
| `issue_source` | `SWEEP` / `REPORT` | 주기 조회 / 보고서 | neutral | |
| `resolved_reason` | `SOURCE_CLOSED` / `NOT_SEEN` / `MANUAL` | 원천 종료 / 미발견 자동 해결 / 수동 해결 | neutral | |
| `job_type` | `COLLECT_AND_RENDER` / `RERENDER` / `RECOLLECT` / `VERIFY` | 생성 / 재생성 / 재수집 / 재현 검증 | neutral / info / info / neutral | |
| `render_mode` | `ORIGINAL` / `RERENDER_LATEST` / `RECOLLECT` | 원본 / 최신 템플릿 재생성 / 재수집 | neutral / info / info | |
| `reproduction` | `VERIFIED` / `DIFFERS` / `UNAVAILABLE` | 재현 일치 / 결과 다름 / 재현 불가 | ok / warn / neutral | |
| `cleanup` | T00 18번에서 확인한 정리 상태 코드 전부 | 예: 정리 가능 / 정리 요청됨 / 정리 완료 / 보존 대상 | | |

알 수 없는 코드는 `neutral` 톤 + "알 수 없음" 라벨(원 코드는 `title`)로 표시하고 서버 로그에 경고를 남깁니다.
매핑은 **한 곳(예: `app/ui/status.py`)** 에만 정의하고 템플릿·JS·보고서 렌더러가 모두 이를 씁니다.

### 5.3 Panel / Card
- `surface` 배경, `border` 1px, `radius-lg`, `shadow-1`, 패딩 `sp-6`(모바일 `sp-4`).
- 헤더: 제목(`fs-lg`) + 설명(`text-muted`, `fs-sm`) + 우측 동작/신선도.

### 5.4 KPI Tile
숫자(`fs-kpi`, tabular) + 라벨 + 보조(변화량·기준 시각). 클릭 가능하면 전체 타일이 링크(해당 필터가 걸린 목록으로).
색 상단 테두리 대신 **아이콘 + 상태 톤 점**으로 구분.

### 5.5 DataTable
- 헤더 `surface-2`, `position: sticky; top: 0`, 정렬 가능한 열은 `aria-sort`.
- 첫 열(식별자) 데스크톱에서 `position: sticky; left: 0`.
- 행 호버 `surface-2`. 행 전체 클릭 시 사이드 시트 또는 상세로 이동(내부 링크는 별도 포커스 가능).
- 행 동작은 우측 `⋯` 메뉴(Popover API). **삭제는 행에 직접 노출하지 않음.**
- `.table-wrap`은 가로 스크롤 시 좌우 가장자리 페이드 그림자(스크롤 위치에 따라 표시)로 "더 있음"을 알림.
- **표 컨테이너 폭이 640px 미만이면 카드 목록으로 전환**(대체로 뷰포트 768px 미만): 각 행 = 제목(고객·계정) + 상태 배지 + 라벨/값 2열 그리드.
  구현: 같은 마크업에 `data-label` 부여 후 컨테이너 쿼리로 표→카드 스타일 전환.
- 빈 상태: 아이콘 + 한 줄 설명 + 다음 행동 버튼(예: "필터 초기화", "일정 등록").

### 5.6 FilterBar
- GET 폼. 필드: 검색(`type=search`, `/` 단축키), 선택형 필터들, 기간(시작·종료 date), "초기화" 링크.
- 적용된 필터는 칩으로 표시(칩의 ×로 개별 해제).
- 값은 쿼리스트링에 유지 → 새로고침·공유·뒤로가기에서 보존.
- JS 활성 시 선택 변경 즉시 제출(검색은 Enter 또는 400ms 디바운스).

### 5.7 Pagination
`이전 · 1 2 3 … 12 · 다음` + "총 N건 · 50행 보기 ▾"(25/50/100/200). 서버 페이지네이션(키셋 또는 offset).

### 5.8 Tabs
링크 기반 탭(`/msp/customer/{id}?tab=automation` 또는 하위 경로). `role="tablist"`는 JS 탭일 때만.
모바일에서는 가로 스크롤 탭 바 + 현재 탭이 보이도록 자동 스크롤.

### 5.9 Side Sheet / Dialog
`<dialog>` + `showModal()`. 오른쪽 시트 폭 `min(560px, 100vw)`. 열릴 때 제목에 포커스, `Esc`·배경 클릭으로 닫힘,
닫으면 원래 트리거로 포커스 복귀. JS 없을 때는 일반 상세 페이지 링크로 동작.

### 5.10 Confirm
- 되돌릴 수 있는 동작(반대 동작 엔드포인트가 있는 것: 일정 중지↔재개, 이슈 확인·음소거↔해제 등): 확인 대화상자 없이 실행 +
  토스트에 **되돌리기** 링크(반대 동작 엔드포인트로 POST). 이 토스트는 10초 유지(6초 규칙의 예외).
- 되돌릴 수 없는 동작: `<dialog>` 확인 — 대상 요약(고객·기간·건수·용량) + 타이핑 확인 + `danger-solid` 버튼.
  네이티브 `confirm()`은 JS 미동작 시 대체 수단으로만.

### 5.11 Toast & 알림함
- 알림 분류는 `success` · `info` · `warning` · `error` 4가지.
- 성공·정보 토스트: 6초 후 자동 소멸, 호버/포커스 시 타이머 정지.
- **`warning`·`error`는 자동 소멸하지 않음.**
- 상단바 종 아이콘 + 안 읽은 개수 → 알림함 팝오버(최근 50건, 읽음 처리, 관련 화면 링크).
- 폴링 주기는 30초(현재 4초) + `document.hidden`이면 중지. 서버가 `Retry-After`를 주면 따름.

### 5.12 Freshness
`<p class="freshness"><time datetime="…">10:30</time> 기준 · 16/16 계정 · 다음 조회 11:00</p>`
커버리지가 100% 미만이면 warn 톤 + "실패 2곳 보기" 링크.

### 5.13 Breadcrumb
`<nav aria-label="현재 위치"><ol>` … 마지막 항목은 `aria-current="page"`. 모든 상세 화면에 필수.
≥768px에서는 상단바에, <768px에서는 상단바가 아니라 **페이지 헤더 첫 줄**에 표시합니다(상단바 공간 부족).

### 5.14 Command Palette
`⌘K`/`Ctrl+K`로 `<dialog>` 열기. 검색 대상: 화면, 고객(이름·코드), 최근 보고서. 서버 엔드포인트
`GET /search?q=` (JSON, 최대 20건, 권한 범위 내). 방향키·Enter 이동, `aria-activedescendant`.

## 6. 포맷 규칙 (공통 헬퍼로만 출력)

| 대상 | 헬퍼 | 출력 예 | 금지 |
|---|---|---|---|
| 일시 | `fmt_dt(dt)` | `2026-09-21 09:02` | `2026-09-21T09:02:18.301468+09:00` |
| 날짜 | `fmt_date(d)` | `2026-09-21 (월)` | |
| 기간 | `fmt_period(a, b)` | 같은 날: `2026-09-20 하루` / 주: `2026-09-15 ~ 09-21` | KST 셀마다 반복 |
| 상대 시각 | `fmt_ago(dt)` | `12분 전` (title에 절대 시각) | |
| 소요 시간 | `fmt_duration(ms)` | `340ms`, `12.4초`, `3분 05초` | 모든 행 `0초` |
| 금액 | `fmt_krw(n)` | `1,422,850원` | |
| 용량 | `fmt_bytes(n)` | `3.18 GiB` | |
| 백분율 | `fmt_pct(x)` | `34.4%` | |

- 시간대는 KST 고정이므로 **표 머리글 또는 페이지 상단에 한 번만** "모든 시각은 KST" 표기.
- 지표 단위는 원천 API 메타데이터에서 가져옵니다. 단위를 모르면 표시하지 않습니다(추측 금지).

## 7. 문구 가이드

- 버튼은 동사로 끝냄: `보고서 생성`, `일정 등록`, `설정 저장`. "확인/취소" 대신 구체적 동작명.
- 오류 메시지 = 무슨 일이 + 왜 + 무엇을 하면 되는지. 예: `수집 권한이 없어 Cloud Insight 이벤트를 가져오지 못했습니다. API 키에 Cloud Insight 조회 권한을 추가한 뒤 다시 실행하세요.`
- 영문 지표명: `메모리 사용률 평균 (Memory Utilization Average)`.
- 기술 내부값(UUID, JSON, enum)은 사용자 문구에 넣지 않음. 필요하면 "기술 상세" `<details>` 안에 키-값으로.

## 8. 접근성 체크

- 모든 입력에 연결된 `<label>`. 오류는 `aria-describedby` + `aria-invalid`.
- 아이콘 전용 버튼 `aria-label` 필수. 장식 아이콘 `aria-hidden="true"`.
- 표 `<th scope>`, 캡션 또는 `aria-labelledby`.
- 실시간 갱신 영역 `aria-live="polite"`, 오류 알림 `role="alert"`.
- 포커스 링: `:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }` — 사이드바에서는 `--nav-current-bar` 색.
- 차트: 데이터 표 대체(`<details>` 안 표) 또는 요약 문장 제공.
