# AGENTS.md — NCP Report Operations Hub

> 이 파일은 저장소 루트에 둡니다. Codex(VS Code 확장/CLI)는 자동으로 읽습니다.
> GitHub Copilot을 쓰는 경우 같은 내용을 `.github/copilot-instructions.md`에도 복사하세요.

## 0. 이 프로젝트가 무엇인가

MSP(클라비)가 NAVER Cloud Platform 고객사별로 **일·주·월간 운영 보고서를 자동 생성·보관·재현**하고,
전체 고객의 **현재 이슈(Cloud Insight 알람)를 한 화면에서 보는** 내부 운영 도구입니다.

제품의 5대 목표 — 모든 변경은 이 중 하나 이상에 기여해야 합니다.

1. 고객사별 리포트 **자동 작성**
2. 리포트 구성 **커스터마이징** (섹션·순서·표시 범위·분석 기준·브랜딩)
3. **스케줄링**에 의한 자동 생성
4. 생성된 리포트 **보관**, 재실행 시 **기존 수집 데이터로 재현**
5. (부가) 주기적 Insight 알람 **전체 조회 → 종합 대시보드의 현재 이슈**

상세 맥락: `docs/redesign/00-context.md` / 디자인 기준: `docs/redesign/01-design-system.md` /
현행 구조(T00 조사 결과): `docs/redesign/current-map.md` / 작업 지시서: `docs/redesign/tasks/T00 ~ T10`.

**결정 기록: `docs/redesign/decisions.md`** — 사용자가 내린 정책 결정(D1~)입니다. 이 파일·지시서와 충돌하면 결정 기록이 우선합니다.
코드에 관한 사실은 `current-map.md`가 지시서 본문보다 우선합니다(8절 참조).

## 1. 작업 방식 (반드시 지킬 것)

- **한 번에 작업 지시서 하나만** 수행합니다. 지시서 범위 밖 파일은 수정하지 않습니다.
- 코드를 바꾸기 전에 **변경 계획**(수정/추가할 파일, DB 마이그레이션 유무, 라우트 변경, 위험 요소)을
  먼저 제시하고 사용자 승인을 받습니다.
- 추측하지 말고 **먼저 코드를 읽고 확인**합니다. 실제 스택과 구조는 T00에서 확인했습니다(6·8절, `current-map.md`).
  지시서 본문과 `current-map.md`가 다르면 `current-map.md`의 사실을 따르고, 그 차이를 계획에 적습니다.
- 작업이 끝나면 **완료 조건 체크리스트**를 하나씩 확인한 결과와 **검증 방법 실행 결과**를 보고합니다.
- 커밋은 지시서 단위로 나누고 Conventional Commits 형식을 씁니다: `feat(portal): 목록 공통 필터·페이지네이션 (T03)`.
  `git add --all` 금지(`git add -p` 또는 파일 지정). `deploy/private/`, `secrets/`, `.env*`는 열지도 수정하지도 않습니다.

## 2. 기술 가드레일

- **서버 렌더링 + 바닐라 JS(점진적 향상)를 유지**합니다. React/Vue/SPA 전환, Tailwind 도입, 빌드 파이프라인
  신설은 하지 않습니다. JS가 꺼져도 핵심 기능(조회·폼 제출)은 동작해야 합니다.
- **외부 CDN 금지.** 폰트·아이콘·스크립트는 `webapp/static/` 아래에 자체 호스팅합니다.
- 새 런타임 의존성 추가는 계획 단계에서 이유를 설명하고 승인받습니다.
- 브라우저 기능은 Baseline 기준으로 씁니다.
  - 자유롭게 사용: CSS 변수, `@layer`, 중첩, `:has()`, 컨테이너 쿼리, `light-dark()`, `oklch()`,
    `<dialog>`, Popover API, `<details>`, 같은 문서 내 View Transitions
  - 대체 수단과 함께만 사용: CSS Anchor Positioning(`@position-try`는 Safari 18.4+),
    문서 간(cross-document) View Transitions(Firefox 미지원), 스크롤 기반 애니메이션(Firefox 미지원)
- **기존 URL은 깨뜨리지 않습니다.** 경로를 바꾸면 이전 경로에서 302/301 리다이렉트를 둡니다.
- **이미 생성·보관된 보고서 HTML은 수정하지 않습니다.** 과거 보고서는 그대로 열려야 합니다(재현성).

## 3. 보안·데이터 가드레일

- Access Key / Secret Key / 세션 / CSRF 토큰을 **로그·화면·예외 메시지·테스트 픽스처에 남기지 않습니다.**
- 상태를 바꾸는 요청은 모두 **POST + CSRF 토큰**입니다. GET으로 상태를 바꾸지 않습니다.
- 파괴적 동작(삭제·오프보딩·대량 정리)은
  - 확인 문구에 **대상(고객명·기간·건수)을 명시**하고,
  - 되돌릴 수 없으면 **타이핑 확인**(고객 코드 등)을 요구하며,
  - 목록 행에 직접 노출하지 않고 상세 화면 또는 `⋯` 메뉴 안에 둡니다.
- 수집·렌더 과정은 **결정적(deterministic)** 이어야 합니다. 렌더 코드 안에서 `now()`, 난수, 정렬되지 않은
  dict/set 순회를 쓰지 않습니다. 시각은 매니페스트에서 주입합니다(T07 참조).
- 인증된 사용자가 `/login`에 오면 역할별 기본 화면으로 리다이렉트합니다(GET은 이미 구현됨 — 재구현하지 말고 회귀 테스트로 유지).

## 4. UI 규칙 요약 (상세는 01-design-system.md)

- 색·간격·글꼴은 **디자인 토큰(CSS 변수)만** 사용합니다. 컴포넌트 CSS에 hex 값을 직접 쓰지 않습니다.
- 상태는 **아이콘 + 한국어 텍스트 + 색**으로 표현합니다. 색만으로 구분하지 않습니다.
- 상태 코드(`SUCCESS`, `PARTIAL_SUCCESS` 등)를 화면에 그대로 출력하지 않습니다.
  반드시 공통 헬퍼 `status_badge(code, kind=None)`(기존 `webapp/presentation.py`의 `format_status`, Jinja 이름 `status_label`을 확장)를 거칩니다. 원 코드는 `title`·`data-code` 속성과 폼 `value`에만 둡니다.
- 시각·기간·금액·용량·소요시간도 공통 포맷 헬퍼만 사용합니다(ISO 원문·마이크로초 출력 금지).
- 내부 데이터(JSON 등)를 사용자에게 원문으로 보여주지 않습니다. 키-값 목록으로 변환합니다.
- 모든 목록은 **필터 + 페이지네이션**을 갖습니다. 한 페이지 기본 50행, 최대 200행.
- WCAG 2.2 AA: 대비 4.5:1(본문), 터치 타깃 최소 24px(모바일 44px), `:focus-visible` 표시, 스킵 링크 유지,
  아이콘 전용 버튼에는 `aria-label`.
- 반응형 기준 폭: **375 / 768 / 1280 / 1440px**. 어느 폭에서도 페이지 가로 스크롤이 생기면 안 됩니다
  (표는 `.table-wrap` 내부 스크롤 허용).
- 화면 문구는 한국어 존댓말 평서형, 간결하게. 영문 지표명은 `한국어 (English)` 형태로 병기합니다.

## 5. 검증 (모든 지시서 공통)

작업 완료 보고에 아래를 포함합니다.

1. 기존 테스트 전체 통과 결과, 새로 추가한 테스트 목록
2. 변경된 화면을 375 / 768 / 1280 / 1440px에서 확인한 결과 (가로 스크롤 여부, 레이아웃 깨짐 여부)
3. 라이트·다크 모드 모두에서 대비 확인 결과
4. 키보드만으로 주요 동작 수행 가능 여부 (Tab 순서, 포커스 표시, Esc로 닫기)
5. 리다이렉트를 추가했다면 이전 URL 접속 결과
6. DB 마이그레이션이 있다면: **추가형(expand/contract) 여부**, 빈 DB에 전체 마이그레이션 2회 적용 결과(재실행 안전성), 기존 데이터 위 적용 결과,
   문제 시 데이터 삭제 없이 되돌릴 **전진 수정 계획**. (이 저장소는 forward-only 원칙입니다. 다운그레이드 스크립트를 만들지 않습니다.)

## 6. 이 저장소의 실제 구조 (2026-10-06 코드 점검 기준)

- 스택: Python 3.13, Flask 3 + gunicorn(`webapp.wsgi:app`), psycopg 3 + **원시 SQL**(ORM 없음), Jinja2 템플릿, 바닐라 JS.
- DB 스키마: `database/schema/NNN_*.sql` 번호순 파일을 `deploy/docker/migrate.sh`가 적용(forward-only). 스키마는 `control`(공용) +
  환경별 `public_data` / `gov_data` + `audit`. **행 수준 보안(RLS)과 역할별 DB 계정**(`ncp_msp_app`, `ncp_public_worker`, `ncp_gov_worker` …)으로 테넌트·환경을 격리합니다.
  새 테이블은 이 배치 원칙과 RLS 정책을 반드시 따릅니다.
- 프로세스: 웹(gunicorn), `webapp.scheduler`(일정 → 작업 생성), `webapp.job_worker --environment public|gov`(작업 실행, `FOR UPDATE SKIP LOCKED`).
  관리 명령은 `python -m webapp.cli`(argparse, `webapp/cli.py:33`).
- 파이프라인: `ncp_api/`(HTTP·서명) → `collectors/` → `normalizers/` → `app/runner.py`(ReportRunner) → `app/report_analysis/`(결정적 분석) → `app/renderers/`(HTML).
- 저장: `database/report_repository.py`(파이프라인 쓰기) + `webapp/repository.py`(포털 읽기·관리) 두 계층. 리포트 산출물은 `REPORT_OUTPUT_DIR`의 파일, 스냅샷은 `{env}_data.report_snapshots`.
- 테스트: 8절의 명령(bare `pytest`는 경로 문제로 실패), DB 통합 테스트는 `REPORT_DB_INTEGRATION_TEST=1` 필요.

## 7. 코드 크기·품질 예산 (AI 생성 코드 비대화 방지)

- 새로 만들거나 크게 고치는 함수는 50줄·순환 복잡도 15 이하, 파일은 800줄 이하. 넘으면 분할한 뒤 병합합니다.
  (기존 대형 파일 `app/renderers/html_renderer.py`, `webapp/repository.py`, `app/runner.py`, `normalizers/billingnormalizer.py`에는 **더 추가하지 말고** 새 모듈로 뺍니다.)
- 새 헬퍼를 만들기 전에 기존 것을 검색합니다(`_as_bool`, `_text`, KST 정의 등이 이미 여러 벌 있습니다). 공용 헬퍼는 한 곳에만 둡니다.
- 새 `except Exception`, 내부 데이터에 대한 `isinstance(x, dict)`, `or {}` 연쇄는 이유를 주석으로 남기거나 쓰지 않습니다.
- 타입 표기는 `X | None`, `list[str]` 형식. 테스트는 소스 텍스트가 아니라 **동작**을 검증하고, 새 skip 조건을 만들지 않습니다.
- 도구 서명 주석(`# ponytail:` 등)을 남기지 않습니다.

## 8. T00 조사 결과 반영 (2026-10-07) — 모든 지시서 공통

지시서 본문은 T00 이전에 운영 화면만 보고 썼습니다. 아래 사실이 지시서 본문과 다르면 **아래가 우선**합니다(근거: `docs/redesign/current-map.md`).
각 지시서 맨 앞의 "현행 반영" 절도 같은 성격입니다.

- **결정 D1–D3**(`docs/redesign/decisions.md`)을 따릅니다. 특히 D1 — **수집은 최대한, 범주 선택은 표시에만**: 범주 선택으로 수집을 줄이는 변경을 하지 않고, UI 이름은 "표시 범위"입니다.
- **경로**: 포털 템플릿·정적 파일은 `webapp/templates/`, `webapp/static/`입니다(루트 `templates/`·`static/` 아님).
  보고서 본문은 Jinja가 아니라 Python 렌더러(`app/renderers/html_renderer.py`, `html_report_styles.py`)입니다.
- **보고서 유형**: `DAILY` · `WEEKLY` · `MONTHLY` · `CUSTOM`. 예전 설계의 `RANGE`는 현행 `CUSTOM`입니다. 새 값을 만들지 않습니다.
- **상태는 두 축**: 작업 `report_jobs.status` = `QUEUED/RUNNING/SUCCESS/FAILED/CANCELLED`,
  보고서 `report_runs.status` = `QUEUED/RUNNING/PARTIAL_SUCCESS/SUCCESS/FAILED/RETRYING/CANCELLED`. `PENDING`은 없습니다(`QUEUED`). 화면에서 두 축을 섞지 않습니다.
- **새 상태·유형 값**(예: `WAITING_DATA`, `job_type`, `LEGAL_HOLD`)은 코드 매핑만이 아니라 SQL CHECK·인덱스 조건·템플릿·필터·알림·기존 데이터 호환을 함께 바꿔야 하므로 계획에서 별도 승인받습니다.
- **관리 명령**: 지시서의 `<cli>` = `python -m webapp.cli`. 새 하위 명령은 argparse에 최소 연결만 하고 처리 코드는 책임 모듈에 둡니다. 비밀번호를 명령줄 인자로 받지 않습니다.
- **설정·보존**: 고객 출력 설정과 보존 정책은 `control.tenant_report_settings.settings` JSON 한 행(schema_version 1.4, `retention_policies.DAILY/WEEKLY/MONTHLY`)입니다. 별도 보존 테이블을 만들지 말고 이 JSON에 키를 추가합니다.
- **일정**: 실제 일정 테이블은 `control.account_report_schedules`(timezone·weekly_day·monthly_day·next_run_at 있음)입니다. 구형 `report_schedules`는 scheduler가 읽지 않으므로 쓰지 않습니다.
- **이미 있는 것 — 다시 만들지 말고 확장**: 포맷·상태 헬퍼 `webapp/presentation.py`(`format_kst` :15, `format_duration` :35, `format_status` :58(Jinja 이름 `status_label`), `inclusive_end` :66),
  `base.html`의 `menu_link` 매크로, 큐 재시도(`webapp/jobs.py:255`, max_attempts 3), HTTP 재시도(`utils/common_rest.py:475`), `ANALYSIS_VERSION`(`app/report_analysis/engine.py:23`, 현재 1.3),
  인증된 GET `/login` 리다이렉트, 오류 토스트 유지, 숨긴 탭 폴링 생략, 설정 변경 감사(`webapp/repository.py:1842–1941`).
- **네트워크가 필요한 단계**(패키지 설치·잠금 파일 생성·취약점 조회·이미지 다이제스트·NCP 공식 문서 확인)는 실행하지 말고 **사용자가 실행할 명령과 확인 방법으로 준비**해 보고합니다. 결과를 추정으로 채우지 않습니다.
- **운영 DB·PVC·실제 NCP API에는 접속하지 않습니다.** 운영에서만 확인할 수 있는 사항은 "미확인 + 확인 방법"으로 남깁니다.
- **테스트 명령**: (PowerShell) `$env:PYTHON_DOTENV_DISABLED=1; .\.venv\Scripts\python -m pytest -q` / (bash) `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q`.
  기준 결과: 620 passed, 5 skipped(DB 통합 테스트 opt-in).
- **줄바꿈**: 작업 트리에 CRLF/mixed 파일 41개가 있습니다. 편집하는 파일의 기존 줄바꿈을 유지하고, 정규화는 T00A A-1에서 명시적 승인 후 단독 커밋으로만 합니다.
