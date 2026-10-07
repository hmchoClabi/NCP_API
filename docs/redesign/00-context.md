# 00. 현재 구조와 목표 구조

> 이 문서는 운영 중인 사이트(architect.clabi.co.kr, **build-46 · d222302**, 2026-10-01)를
> MSP 관리자 계정으로 직접 조회해 측정한 사실입니다. 코드가 아니라 **화면과 HTML 기준**이므로,
> T00에서 코드와 대조해 차이가 있으면 `docs/redesign/current-map.md`에 기록하세요.
>
> **2026-10-07 갱신**: T00 조사(`current-map.md`)로 코드 기준 사실이 확인되어 이 문서의 2·3·5·6·10·11절을 고쳤습니다.
> 코드에 관한 사실은 `current-map.md`, 정책 결정은 `decisions.md`가 이 문서보다 우선합니다.

---

## 1. 현재 사이트맵

| 메뉴 그룹 | 화면 | URL | 역할 | 실측 |
|---|---|---|---|---|
| MSP 운영 | 통합 대시보드 | `/msp` | 금일 Insight 알람, 저장공간, 고객 수, 어제 이후 점검 항목 | 패널 4개 |
| | 민간 고객 | `/msp/customers/public` | 민간 고객 카드 목록 + 신규 등록(`<details>`) | 8곳, 검색 없음 |
| | 공공 고객 | `/msp/customers/gov` | 공공 고객 카드 목록 + 신규 등록 | 8곳, 검색 없음 |
| | 전체 실행 일정 | `/msp/schedules` | 일정 일괄 추가·갱신·삭제, 보존 정책 일괄 적용, 등록 일정 목록 | 일정 8개 |
| 보고서 | 전체 고객 보고서 | `/portal` | 고객 표 + 최근 보고서 100행 + 최근 작업 100행 | 112KB, DOM 3,228, 필터 없음 |
| | 생성 이력 | `/history` | 실행 이력 | 필터(고객·검색·결과) + 50행 페이지 |
| 관리 | MSP 계정·사용자 관리 | `/msp/users` | MSP 계정·고객 사용자 등록/권한 | 폼 3개(`<details>`) + 표 2개 |
| | 데이터 정리 | `/msp/data-cleanup` | 보고서 산출물 선택 정리 | 112행, 88KB, 필터 없음 |
| (메뉴 외) | 고객 상세 | `/msp/customer/{tenant_id}` | 아래 3절 | 섹션 8개, 폼 14개 |
| | 보고서 뷰어 | `/reports/{report_id}` | 툴바 + `<iframe src=".../content">` | |
| | 보고서 본문 | `/reports/{report_id}/content` | 자체 완결형 HTML 산출물 | 약 860KB, 표 16개, `<details>` 31개 |
| | 로그인 | `/login` | | 인증 상태에서도 렌더링됨(운영 관찰. 코드에는 인증된 GET 리다이렉트가 이미 있음 — T00) |

## 2. 정적 자산

| 파일 | 크기 | 비고 |
|---|---|---|
| `webapp/static/portal.css` | 7.4KB | 기본 토큰(`--ink`, `--muted` 등) + 셸 + 공통 컴포넌트 |
| `webapp/static/automation.css` | 6.4KB | `.secondary`, `.status.*`, 계정·자동화 블록, 보고서 뷰어 |
| `webapp/static/notifications.css` | 3.1KB | 토스트 알림 |
| `webapp/static/report_settings.css` | 4.6KB | 출력 설정 화면 |
| `webapp/static/ux.css?v=build-46` | 3.3KB | **덮어쓰기 패치 레이어** (`!important` 포함). 포커스·스킵링크·현재 메뉴·햄버거·표 스크롤 안내·필터·페이지네이션 등 |
| `webapp/static/portal.js?v=build-46` | | 보존정책 토글, 정리 선택, 알림 폴링(4초, 숨긴 탭 생략), 일반·경고 토스트 6초 자동 소멸(오류 토스트는 유지) |
| `webapp/static/favicon.svg` | | build-46에서 추가 |

중단점은 `1000px`, `720px` 두 개가 여러 파일에 **중복 정의**되어 있고, `ux.css`가 앞선 파일들을 덮어씁니다.
→ T01에서 토큰 + `@layer` 구조로 통합합니다.

## 3. 고객 상세 화면 (`/msp/customer/{tenant_id}`) — 커스터마이징·자동화의 중심

한 페이지에 h2 섹션 8개가 세로로 이어집니다.

1. **고객사 로고** — 파일 업로드 / HTTPS URL 가져오기 / 삭제 (폼 3개)
2. **NCP 계정 및 보고서 자동화** (계정 단위 `account_id`)
   - 즉시 생성: `POST /accounts/{account_id}/report-jobs` + hidden `report_type`(`DAILY`·`WEEKLY`·`MONTHLY`, 시간 범위는 `CUSTOM`).
     입력: 일일 `date` · 주간 `week` · 월간 `month` · 시간 범위 `datetime-local` 2개
   - 자동 실행 일정: `POST /accounts/{account_id}/schedules`
     - 일일: 시·분 / 주간: 요일 + 시·분 / 월간: **1–28일** + 시·분 (말일 선택 불가, 시간대 KST 고정)
   - API 키 삭제(계정 코드 타이핑 확인)
3. **고객별 보고서 출력 설정** — `POST /msp/customer/{tenant_id}/report-settings` **하나의 거대한 폼**
   - 섹션 8개 on/off + 순서(`section_order` hidden ×8, ↑↓ 버튼):
     `infrastructure_inventory`, `monitoring`, `executive_summary`, `organization_billing`, `billing`,
     `insight_events`, `activity_history`, `collection_diagnostics`
   - 보존 정책: 일일/주간/월간 각각 `DAYS`(1–3650일) | `FOREVER`
   - 자원 범주 34개 체크박스 (`resource_categories`) — **표시 범위**(결정 D1: 수집은 줄이지 않음)
   - 모니터링 범주 11개 체크박스 (`monitoring_categories`) — 표시 범위
   - 수집 옵션: `analysis_enabled`(결정론적 운영 분석), `collect_wms`, `collect_security_monitoring`
   - 분석 임계치 11개: CPU/메모리/스토리지 주의·위험(현행 최소 90% → **결정 D3로 50%까지 완화**, 기본값 유지), 지속 시간(분),
     비용 증가 주의(%), 가용성 주의·위험(%), 응답시간 주의(ms)
4. **API 키 등록·교체** — 계정 코드, 표시 이름, Access/Secret Key → "암호화하여 저장"
5. 연결된 사용자 / 6. 최근 생성 작업 / 7. 최근 생성 보고서 / 8. **고객 오프보딩**(고객 코드 타이핑 확인)

브레드크럼: `민간 고객 / 클라비` (build-46에서 추가)

## 4. 보고서 뷰어·본문

- 툴바(build-46): `인쇄 · PDF 저장`, `모두 펼치기`, `모두 접기`(iframe 로드 후 활성화), 상태 배지(`부분 수집`, `title="PARTIAL_SUCCESS"`),
  `새 창에서 보기`, `보고서 삭제`(확인 문구에 고객명·기간 포함)
- 본문 HTML 메타데이터는 `<meta name="report-id" content="20260930_20260930">` **하나뿐**입니다.
  어떤 수집 스냅샷·설정·템플릿 버전으로 만들어졌는지 기록이 없습니다.
- 본문에는 인쇄 CSS(A4 가로, 섹션 나눔 방지, 부록 자동 펼침), `prefers-reduced-motion`, 차트별 PNG 저장이 이미 있습니다.
- 확인된 결함: 차트 범례(`.chart-legend-item`)에 폭 제한이 없어 긴 볼륨 경로가 모바일에서 문서 폭을 928px까지 늘림,
  인쇄 시 범례 숨김(`.chart-legend{display:none}`), 사용률 차트 Y축 0–100% 고정, 생성 시각 ISO 원문(마이크로초 포함),
  차트 제목만 영문.

## 5. 이력·재현

- `/history`의 각 행 마지막 열 **"재현하기"는 `<a href="/reports/{id}">` 링크일 뿐**입니다.
  보고서를 다시 렌더링하거나 저장된 데이터로 재구성하는 기능은 **존재하지 않습니다.**
- `/history`에서 `PARTIAL_SUCCESS`가 `.status.ok`(초록) 클래스로 표시됩니다(뷰어에서는 `warn`). 상태 표현이 화면마다 다릅니다.
- 보고서 삭제 문구 "이 보고서와 **관련 수집 데이터**를 삭제" → T00 확인: 내부 스냅샷·시계열·네트워크 규칙은 DB 환경별 스키마
  (`report_snapshots`, `metric_series`, `network_configuration_snapshots` 등)에, HTML·공개 JSON은 `REPORT_OUTPUT_DIR` 파일에 있습니다.
  보고서 삭제 시 FK CASCADE로 함께 삭제되고 파일은 정리 outbox로 지워집니다(current-map 7절).
  PVC 9.75GiB는 2026-10-01 운영 관측값이며 현재 실제 용량은 미확인입니다(Helm 기본값 20Gi).

## 6. 스케줄 현황 (2026-10-01)

- 등록 일정 **8개, 전부 `일일 · 매일 09:00 KST`**. 고객 16곳 중 **8곳은 자동화되어 있지 않고**, 주간·월간 일정은 **0개**입니다.
- 모든 일정이 **같은 분(09:00)에 동시에 실행**됩니다 → NCP API 호출 집중, 실패 시 전부 함께 실패할 위험.
- 일정 단위는 계정(`account_id`)이며, 출력 설정은 고객(`tenant_id`) 단위 하나뿐이라
  **일·주·월 보고서가 모두 같은 섹션 구성**을 씁니다.
- 실패 시 큐 재시도(최대 3회)는 코드에 이미 있으나 화면에 드러나지 않습니다. 데이터 준비 대기(월간 확정 청구), 완료 후 전달(메일·링크) 설정은 없습니다.

## 7. 통합 대시보드의 Insight 알람

- 패널 제목 "금일 수집 Cloud Insight 알람". **오늘 완료된 보고서에 포함된 알람을 모은 것**이며
  화면에도 "실시간 상태가 아니며 발생일은 오늘 이전일 수 있습니다"라고 적혀 있습니다.
- 중복 제거 규칙(유지할 것): 고객·계정·인스턴스·알람 규칙·지표·조건이 같으면 하나로 묶음.
  NKS CronJob은 클러스터·네임스페이스·작업 기준으로 묶음. (요약입니다. 정확한 그룹 키는 current-map 8.1과 `webapp/insight_dashboard.py`)
- 결함: "대상 상세"에 원시 JSON 노출(`{"clusterUUID": ...}`), 조건 표기 `real_mem >= 90 bytes`(단위 확인 필요),
  "정보" 등급이 `.status.pending` 클래스 사용, "0건 종료 미확인" 같은 모호한 문구.
- 보고서 생성과 **분리된 주기 조회가 없어서**, 보고서를 만들지 않는 고객(현재 8곳)의 이슈는 대시보드에 나타나지 않습니다.

## 8. build-46에서 이미 개선된 것 (다시 하지 말 것)

현재 메뉴 표시(`aria-current`, `.is-current`), 메뉴 그룹 재편(관리 그룹 분리), 그룹 라벨 `grid-column:1/-1`,
1000px 이하 햄버거(`.menu-toggle`), 스킵 링크, `:focus-visible`, `--muted` 대비 개선(#5b6a7f), 파비콘,
`/history` 필터·페이지네이션, 고객 상세 브레드크럼, 등록 폼 `<details>` 접기, 표 스크롤 안내 문구,
터치 타깃 최소 높이, `prefers-reduced-motion`, 보고서 뷰어 인쇄·펼치기 버튼, 삭제 확인 문구에 대상 명시.

→ 문제는 이것들이 **`ux.css` 덮어쓰기 패치로 누적**되고 있다는 점입니다. 기능 개선을 이어가기 전에
디자인 시스템을 한 번 정리해야 이후 작업이 안전합니다(T01).

---

## 9. 5대 목표 대비 현황과 갭

| 목표 | 현재 지원 | 갭 | 해결 지시서 |
|---|---|---|---|
| ① 고객사별 자동 작성 | 계정별 즉시 생성 4종, 일정 기반 생성 | 16곳 중 8곳 미자동화를 한눈에 볼 화면 없음, 실행 결과 집계 없음 | T04, T06 |
| ② 커스터마이징 | 섹션 on/off·순서, 자원/모니터링 범주, 임계치, 로고 | 고객당 설정 1벌(보고서 유형별 구성 불가), 재사용 템플릿 없음, 미리보기 없음, 설정 변경 이력 화면 없음, 4가지 관심사(구성·표시 범위·분석·보존)가 한 폼 | T04, T05 |
| ③ 스케줄링 | 일·주·월, 일괄 등록, 중지, 큐 재시도(화면 미노출) | 말일·지터·데이터 준비 대기 없음, 재시도 상태 미표시, 타임라인 없음, 실패 알림 없음, 전달 없음 | T06 |
| ④ 보관·재현 | 유형별 보존 기간, 산출물 정리 화면 | 수집 스냅샷·설정·템플릿 버전 미기록, **재현 기능 없음**("재현하기"는 링크), 산출물과 원천 데이터 보존 분리 불가 | T07, T08 |
| ⑤ 현재 이슈 대시보드 | 오늘 보고서 기반 알람 집계 | 보고서와 독립된 주기 조회 없음, 이슈 상태(확인·해결·음소거) 없음, 조회 신선도·커버리지 표시 없음, 알림 이력 없음 | T09 |

---

## 10. 목표 구조

### 10.1 목표 사이트맵

```
운영
├─ 통합 대시보드        /msp                 현재 이슈 · 오늘 실행 결과 · 미자동화 고객 · 저장공간
├─ 현재 이슈            /msp/issues          [신규] 주기 조회 기반 이슈 목록·상태 관리
└─ 고객                 /msp/customers/all   [통합] 탭(경로): 전체 all | 민간 public | 공공 gov, 검색
     └─ 고객 워크스페이스 /msp/customer/{id}   탭: 개요 | 보고서 | 자동화 | 출력 설정 | 계정·API 키 | 사용자 | 위험 영역
자동화
├─ 실행 일정            /msp/schedules       목록 + 14일 타임라인
└─ 리포트 프로필        /msp/profiles        [신규] 재사용 가능한 보고서 구성 템플릿
보고서
├─ 보고서 보관함        /portal              필터: 고객·유형·기간·상태·버전 (산출물 중심)
└─ 실행 이력            /history             실행 단위 로그: 성공/부분/실패, 재시도, 재현 (실행 중심)
관리
├─ 계정·사용자          /msp/users
└─ 저장공간·보존        /msp/data-cleanup    저장공간 현황 + 보존 정책 + 정리 (원천 데이터/산출물 분리)
```

- 고객 목록은 현행처럼 환경을 **경로**로 둡니다(`/msp/customers/<environment>`, `all` 신규). 기존 `/public`·`/gov` URL은 그대로 동작하므로 리다이렉트가 필요 없고, 접미사 없는 `/msp/customers`만 `/msp/customers/all`로 302.
- 기존 `/portal`, `/history` URL은 유지하고 **역할과 라벨만 분리**합니다.

### 10.2 목표 데이터 흐름

```
                ┌──────────── 리포트 프로필 (버전 관리) ────────────┐
                │ 섹션·순서 · 표시 범위 · 분석 임계치 · 브랜딩     │
                └───────────────┬─────────────────────────────────┘
                                │ settings_snapshot (렌더 시점 고정)
일정/수동 요청 ──► [1. 수집 Collect] ──► 수집 스냅샷 (불변, sha256, 압축 JSON)
                                │
                                ▼
                     [2. 분석 Analyze]  결정적: 같은 입력 → 같은 판정
                                │
                                ▼
                     [3. 렌더 Render]   결정적: 시각·버전은 매니페스트에서 주입
                                │
                                ▼
                     보고서 산출물 HTML + manifest.json (스냅샷·설정·템플릿·분석 버전, 해시)

재현 = 같은 스냅샷 + 같은 설정 스냅샷 → 2·3단계만 다시 실행 (외부 API 호출 없음)
재수집 = 1단계부터 새로 실행 → 같은 보고서의 새 버전

[Insight 주기 조회] ─(N분마다, 알람 API만)─► insight_issue (지문 기준 upsert, 상태 머신) ─► 대시보드·현재 이슈·알림함
```

### 10.3 지시서 순서와 의존성

```
T00 저장소 조사 (코드 변경 없음)
 └─ T00A 엔지니어링 기반 정비 ─ T00B 보안·성능 긴급 수정
     └─ T01 디자인 토큰·CSS 레이어 통합
         └─ T02 앱 셸·내비게이션
             └─ T03 목록 공통 패턴 (필터·페이지네이션·모바일 카드)
                 ├─ T04 고객 워크스페이스 (탭 재구성·설정 폼 분리)
                 │   └─ T05 리포트 프로필
                 │       └─ T06 스케줄링 고도화
                 │           └─ T07 수집 스냅샷·재현
                 │               └─ T08 보고서 뷰어·산출물 품질
                 └─ T09 Insight 주기 조회·현재 이슈 대시보드  (T04–T08과 병행 가능)
T10 품질 점검 (마지막, 또는 각 단계 후 부분 실행)
```

---

## 11. 공통 열거형과 이름 규칙

T00에서 확인한 **현행 값**이 기준입니다(근거: `current-map.md` 12절). 새 값을 만들지 말고 아래를 씁니다.
새 상태·유형을 추가해야 하면 SQL CHECK·인덱스 조건·템플릿·필터·알림·기존 데이터 호환을 함께 바꾸는 계획을 별도 승인받습니다.
문자열 전면 치환은 하지 않습니다(DB·CLI·폼 값의 호환은 한 매핑 경계에서 유지).

| 개념 | 값 | 비고 |
|---|---|---|
| 보고서 유형 `report_type` | `DAILY` · `WEEKLY` · `MONTHLY` · `CUSTOM` | 폼·DB·CLI 공통. 예전 설계의 `RANGE` = 현행 `CUSTOM`(시간 범위). URL 쿼리에서는 소문자도 허용 |
| 기간 값 | DAILY `YYYY-MM-DD` · WEEKLY `YYYY-Www`(ISO 주, 월요일 시작) · MONTHLY `YYYY-MM` · CUSTOM `start_datetime`/`end_datetime` | CUSTOM은 KST 해석, 종료 미포함, 같은 달 안 |
| 프로필 대상 유형 | 위 4개 + `ANY` | `ANY`는 프로필·고객 설정 전용(실행 유형 아님, T05 신규) |
| 일정 주기 | 일정의 `report_type`이 곧 주기 (`DAILY`=매일, `WEEKLY`=매주, `MONTHLY`=매월) | `CUSTOM`은 일정 불가(수동 전용) |
| 작업 상태 `report_jobs.status` | `QUEUED` · `RUNNING` · `SUCCESS` · `FAILED` · `CANCELLED` | `PENDING`은 없음. `PARTIAL_SUCCESS`는 작업 상태가 아님 |
| 보고서 상태 `report_runs.status` | `QUEUED` · `RUNNING` · `PARTIAL_SUCCESS` · `SUCCESS` · `FAILED` · `RETRYING` · `CANCELLED` | 작업 상태와 다른 축. 이력 화면은 두 축을 구분해 표시 |
| 데이터 대기 | `WAITING_DATA` | **신규(아직 없음)**. T06에서 승인 시 추가 |
| 실행 계기 `trigger_type` | `MANUAL` · `SCHEDULED` · `RETRY` | 작업 유형과 다른 축 |
| 작업 유형 `job_type` | `COLLECT_AND_RENDER` · `RERENDER` · `RECOLLECT` · `VERIFY` | **신규(현행 컬럼 없음)**, T07 |
| 데이터셋 상태 | `NOT_REQUESTED` · `PARTIAL` · `FAILED` · `COLLECTED` · `COLLECTED_EMPTY` | 수집 품질 표시용 |
| 고객 `tenants.status` | `ACTIVE` · `SUSPENDED` · `ONBOARDING` · `OFFBOARDED` | |
| 계정 `cloud_accounts.status` | `ACTIVE` · `DISABLED` · `CREDENTIAL_ERROR` | 사용자 상태와 섞지 않음 |
| 사용자 `users.status` | `INVITED` · `ACTIVE` · `LOCKED` · `DISABLED` | 역할·소속과 별개 |
| 역할 | 플랫폼 `MSP_OPERATOR` · `MSP_ADMIN` · `SYSTEM_ADMIN` · `SECURITY_AUDITOR` / 고객 `CUSTOMER_ADMIN` · `CUSTOMER_VIEWER` | 이름만으로 권한을 넓히지 않음(`SYSTEM_ADMIN`을 `MSP_ADMIN`과 자동 동등 취급 금지). 사용자는 여러 고객에 소속 가능 |
| 분석 이슈 `event_cases.status` | `NEW` · `ACKNOWLEDGED` · `IN_PROGRESS` · `RESOLVED` · `IGNORED` · `NOT_DETECTED` | T09 이슈 상태와 직접 치환 금지 |
| 보존 정책 | `DAYS`(1–3650) · `FOREVER`, 유형별 DAILY/WEEKLY/MONTHLY | `tenant_report_settings.settings.retention_policies` |
| 시간대 | `Asia/Seoul` | 일정 테이블에 `timezone` 컬럼이 있으나 값은 KST 유지. 화면에는 "모든 시각은 KST" 한 번만 표기 |
| 요일 | ISO 8601 (1=월 … 7=일) | 일정 컬럼 `weekly_day` |
| 관리 명령 | `python -m webapp.cli` | 지시서의 `<cli>` 자리 |

---

## 12. 코드 점검 결과 요약 (2026-10-06, HEAD d222302)

- 규모: 추적 파일 256개, 앱 코드 약 47,900줄, 테스트 22,800줄(620개 통과, 커버리지 73.8%: ncp_api 38% · database 53% · webapp 61%).
- 대형 파일: `app/renderers/html_renderer.py` 5,352줄 · `webapp/repository.py` 4,285줄 · `normalizers/billingnormalizer.py` 2,954줄 · `app/runner.py` 2,900줄.
- 실제 구조와 저장소 규칙은 `AGENTS.md` 6절, 크기·품질 예산은 7절을 따릅니다.
- **UI 개편(T01~) 전에 T00A(엔지니어링 기반)와 T00B(보안·성능 긴급 수정)를 먼저 진행**합니다.
- 상세 근거: `docs/reviews/2026-10-06-code-review.html`
- **T00 조사 결과**: `docs/redesign/current-map.md`(2026-10-06, 커밋 8d2e310). 10절 판정에 따라 2026-10-07 지시서 전체를 수정했습니다.
- **정책 결정**: `docs/redesign/decisions.md` — D1 수집 최대·선택은 표시에만, D2 단건 삭제 운영자 허용 + 최신본 보호, D3 임계치 하한 50%·기본값 유지.
