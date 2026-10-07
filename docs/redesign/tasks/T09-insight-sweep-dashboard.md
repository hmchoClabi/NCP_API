# T09 — Insight 알람 주기 조회와 "현재 이슈" 통합 대시보드

> 선행: T03 (T04–T08과 병행 가능). 기준: `00-context.md` 7절, `01-design-system.md` 1·5.4·5.11·5.12절.
> T00 **8절**(현재 알람 패널의 데이터 출처·중복 제거 코드·사용 API)을 그대로 재사용하세요.
> 관리 명령은 `python -m webapp.cli`입니다.

## 현행 반영 (T00 결과, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **현재 패널 출처**: `webapp/repository.py:1604`(최근 완료 보고서 + `report_snapshots`) → `webapp/insight_dashboard.py:9`(오늘 완료 보고서 선별·그룹).
  그룹 키·CronJob 규칙과 회귀 테스트(`tests/test_insight_dashboard.py:28,46,58,77,99`)를 **그대로 재사용**합니다.
- **지문과 발생 고유키를 분리**합니다. `fingerprint` = 이슈 그룹 키(기존 그룹 규칙), `occurrence_key` = `source_event_id`가 있으면 그것,
  없으면 `sha256(occurred_at + 정렬된 전체 차원(Pod·node 포함))`. 유일성은 `UNIQUE(fingerprint, occurrence_key)`. `occurred_at`만 쓰면 같은 순간 여러 Pod에서 난 별개 이벤트를 잃습니다.
- **`insight_events.report_run_id`는 NOT NULL**이라 보고서 없는 sweep이 그대로 넣을 수 없습니다. 계획에서 하나를 고르고 이유를 적으세요:
  (a, 권장) 환경별 스키마에 sweep 전용 발생 테이블 신설(RLS 동일), (b) `report_run_id`를 nullable로 바꾸는 추가형 마이그레이션 + 기존 부분 unique `(run, source_event_id, occurred_at)`·조회 영향 검토.
- **`control.event_cases`**(분석 이슈, `NEW/ACKNOWLEDGED/IN_PROGRESS/RESOLVED/IGNORED/NOT_DETECTED`)는 T09 이슈 상태와 다른 개념입니다. 상태를 직접 치환·공유하지 말고 필요하면 비교·링크만 합니다.
- **API 능력**(current-map 8.2): 클라이언트에 미종료 옵션 `only_fetch_un_close_event`(`ncp_api/cloudinsightAPI.py:153`, 이벤트 조회 :109)가 이미 있으나 "현재 열린 알람 전체 목록"을 보장하는지 **공식 확인이 안 됐습니다.**
  확인 전에는 `NOT_SEEN` 자동 해결을 **켜지 않습니다**(경로는 코드에 두되 설정으로 비활성, 테스트로 비활성 확인). `endTime`·`notificationStatus`의 종료 의미도 미확인이므로
  `SOURCE_CLOSED`는 확인된 필드 의미로만 판단합니다.
- 0절의 공식 문서 확인은 네트워크가 필요합니다. Codex는 확인 방법(문서 위치·확인할 필드 표)을 준비하고, 사용자가 확인한 결과를 받아 반영합니다.
- 주기 작업은 기존 프로세스 구조(`webapp/scheduler.py` 루프 또는 별도 프로세스) 위에 두되 `report_jobs` 큐를 그대로 쓰지 않습니다(1절). HTTP Retry-After·백오프 지터·타임아웃은 T00B-8 규칙을 재사용합니다.
- 알림함(T02)이 승인·구현되지 않았으면 7절 알림은 인터페이스만 두고 보고합니다.

## 목표
보고서 생성과 **독립적으로**, 주기적으로 모든 활성 고객 계정의 Cloud Insight 알람/이벤트만 **최소 범위로 조회**해
"지금 열려 있는 이슈"를 통합 대시보드 맨 위에서 보여줍니다.

현재 "금일 수집 Cloud Insight 알람" 패널은 **오늘 완료된 보고서에 포함된 알람**의 집계라서
(화면 문구: "실시간 상태가 아니며 발생일은 오늘 이전일 수 있습니다")
- 보고서를 만들지 않는 고객(현재 8곳)의 이슈는 보이지 않고,
- 하루 1회(09:00) 이후 발생한 알람은 다음 날까지 보이지 않으며,
- 이슈를 확인·해결·음소거로 관리할 수 없습니다.

## 0. 착수 전 확인 (계획에 결과를 적을 것)
T00 8절과 NCP Cloud Insight API 문서를 보고 다음을 확인합니다(공식 문서 확인은 사용자가 수행, 위 현행 반영 절). 이 답에 따라 3절 상태 전이 중 쓸 수 있는 경로가 달라집니다.
1. 이벤트 조회 API가 **종료 시각/종료 상태**를 주는가? → 주면 `SOURCE_CLOSED` 사용 가능
2. **현재 발생 중인 알람 목록**(상태 조회형) API가 있는가? → 있으면 `NOT_SEEN` 사용 가능
3. 지표 단위를 응답에서 얻을 수 있는가? (`real_mem >= 90 bytes` 표기 검증용)
4. 계정당 호출 한도(rate limit)

## 1. 주기 조회 작업 `insight_sweep`
- 주기: 설정값 `INSIGHT_SWEEP_INTERVAL_MINUTES`(기본 30, 최소 10). scheduler 루프 안의 별도 주기 함수(또는 별도 프로세스·CronJob)로 실행합니다.
  `report_jobs`는 보고서 유형 CHECK·`(account, type, period_key)` 부분 unique가 걸린 보고서 큐이므로, sweep을 여기에 넣으려면 새 유형 값으로 계획에서 승인받습니다(AGENTS.md 8절).
- 대상: `ACTIVE`·`ONBOARDING` 고객의 유효한 API 키를 가진 모든 계정.
- 호출 범위: **알람/이벤트 API만**(0절 1·2번). 자원 인벤토리·청구·Activity Tracer 등은 호출하지 않음.
  - 이벤트 조회 구간 = 계정별 `last_window_end - 5분` ~ `now` (최초·장기 실패 후에는 최대 24시간 전부터). 겹침 5분은 누락 방지용이며 중복은 지문·UNIQUE로 제거.
  - 0절 2번 API가 있으면 같은 주기에 현재 발생 목록도 조회.
- 동시성: 계정당 1, 전역 `INSIGHT_SWEEP_CONCURRENCY`(기본 4). 429/5xx는 T00B-8의 Retry-After·지터 백오프 재사용, 계정별 타임아웃 30초.

## 2. 데이터 모델

> 환경별 `{public,gov}_data.insight_events`에는 보고서 수집 시 쓰기가 이뤄지지만(`database/report_repository.py:848-892`) 대시보드는 읽지 않고
> 리포트 스냅샷 JSONB를 파싱합니다(`webapp/insight_dashboard.py`, 복잡도 57). `control.v_all_insight_events` 뷰도 미사용입니다.
> `insight_events.report_run_id`가 NOT NULL이므로, sweep 발생 저장 방법은 위 현행 반영 절의 (a)/(b) 중에서 고릅니다. 새 테이블은 환경별 스키마·RLS 배치를 따르세요.
```
insight_sweep_run
  id · started_at · finished_at · accounts_total · accounts_ok · accounts_failed
  issues_opened · issues_updated · issues_resolved · failures (json: [{account_id, error_code, message_masked}])

insight_sweep_account_state            -- 계정별 진행 상태
  account_id (PK) · last_success_at · last_window_end · consecutive_failures · last_error_code · last_sweep_id

insight_issue
  fingerprint (PK, sha256)   -- webapp/insight_dashboard.py의 기존 그룹 키 함수를 그대로 사용(current-map 8.1):
                             --   고객·계정·환경 + 상품 + 자원 + 규칙 + 지표/조건/단위/집계/간격 + 정렬된 차원
                             --   CronJob controller·클러스터/namespace/Pod가 모두 식별될 때만 Pod·node 차원 제외
                             --   (요약을 보고 새 해시를 짜지 말 것 — 기존 함수 재사용)
  tenant_id · account_id · severity (CRITICAL | WARNING | INFO)
  resource_label · resource_ref (json) · rule_name · metric · condition_text · unit (nullable)
  state (OPEN | ACKNOWLEDGED | RESOLVED | STALE | MUTED) · pre_mute_state (nullable)
  first_seen_at · last_seen_at · last_occurred_at · occurrence_count · last_value · reopened_count
  acknowledged_by · acknowledged_at · muted_until · muted_by
  resolved_at · resolved_reason (SOURCE_CLOSED | NOT_SEEN | MANUAL) · resolved_by
  sources (json array: SWEEP, REPORT) · last_sweep_id

insight_occurrence
  id · fingerprint · occurrence_key · occurred_at · ended_at · value · source_event_id · dimensions (jsonb) · sweep_id · report_run_id (nullable)
  UNIQUE(fingerprint, occurrence_key)   -- occurrence_key = source_event_id 또는 sha256(occurred_at + 정렬된 전체 차원)

insight_issue_event                    -- 상태 변경·메모 이력
  id · fingerprint · at · actor (user id 또는 'system') · from_state · to_state · reason · note
```

## 3. 상태 전이
```
신규 발생 ─► OPEN ─(확인)─► ACKNOWLEDGED          ※ ACKNOWLEDGED는 아래 자동 전이에서 OPEN과 동일하게 취급
               │
               ├─ 원천이 종료를 보고(0절 1번 가능 시) ─────────────► RESOLVED (SOURCE_CLOSED)
               ├─ 현재 발생 목록에서 INSIGHT_NOT_SEEN_MINUTES(기본 120분) 동안 미발견
               │    (0절 2번 API를 쓸 때만) ─────────────────────► RESOLVED (NOT_SEEN)
               ├─ 위 두 방법을 쓸 수 없고 마지막 발생 후 INSIGHT_STALE_HOURS(기본 24시간) 경과 ─► STALE "종료 미확인"
               ├─ 사용자 "해결 처리"(메모 필수) ───────────────────► RESOLVED (MANUAL)
               └─ 사용자 음소거(1시간/1일/7일) ─► MUTED (pre_mute_state 저장) ─(만료/해제)─► pre_mute_state 복원
RESOLVED·STALE 상태에서 같은 지문 재발생 ─► OPEN (reopened_count+1, "재발" 표시)
```
- 기준은 횟수가 아니라 **시간(분/시간)** 입니다. 주기를 바꿔도 의미가 같도록.
- 모든 전이는 `insight_issue_event`에 기록. 현재 화면의 "0건 종료 미확인" 문구는 `STALE` 배지 "종료 미확인"으로 대체.

## 4. 보고서 수집에서 들어오는 알람 (`source=REPORT`)
- 보고서 수집 파이프라인도 같은 upsert 함수를 호출하되, 규칙을 다르게 적용합니다.
  - 기존 이슈가 있으면 occurrence 추가·`last_occurred_at` 갱신만.
  - 기존 이슈가 없으면 **발생 시각이 최근 24시간 이내인 경우에만** 새 이슈를 OPEN. 그보다 오래된 알람은 occurrence만 저장(이슈 미생성).
  - `source=REPORT` 경로에서는 **알림을 보내지 않습니다.**
- 연결 지점: T07이 이미 반영되었다면 "스냅샷 저장 완료" 직후, 아니라면 기존 수집 완료 지점. T07과 동시에 진행 중이면 병합 순서를 계획에 적으세요.

## 5. 통합 대시보드 `/msp` 재배치 (위에서 아래로)
1. **현재 이슈** 패널 (신규, 최상단)
   - 신선도 줄: `10:30 기준 · 16/16 계정 조회 · 다음 11:00` (실패 계정 있으면 warn 톤 + "조회 실패 2곳" 링크).
   - KPI 타일 4개: `위험 N` / `주의 N` / `신규(최근 24시간) N` / `확인 대기 N` — 클릭 시 `/msp/issues`에 해당 필터.
   - 이슈 목록 상위 10건: 심각도 → 최근 발생 순. 열: 심각도 배지 · 고객·계정 · 대상 · 규칙·조건 · 최근 발생(`fmt_ago`) · 횟수 · 상태 · `⋯`(확인, 음소거, 해결 처리, 근거 보기, 고객으로 이동).
   - 이슈 0건이면 "열린 이슈가 없습니다 · 10:30 기준" 빈 상태(조회 실패가 있으면 빈 상태 대신 경고).
2. **오늘 실행** 위젯 — T06이 완료된 경우에만. 아니면 생략하고 완료 보고에 "T06 후 추가 필요"로 남김.
3. **어제 이후 MSP 점검 항목** (기존 유지 — "왜 확인해야 하나 / 어떻게 점검하나" 열은 좋은 설계이므로 보존)
4. **보고 기간 알람** — 기존 "금일 수집 Cloud Insight 알람" 패널은 제목을 이렇게 바꾸고 기본 접힘(보고서 기반 집계임을 명확히).
5. **저장공간**·고객 수 요약은 맨 아래 작은 타일로.

## 6. `/msp/issues` 현재 이슈 화면
- 사이드바 "운영" 그룹에 **현재 이슈** 메뉴를 추가합니다(T02에서 보류한 항목). 열린 위험 이슈 수 배지.
- T03 목록 패턴. 필터: 상태(기본 OPEN+ACKNOWLEDGED), 심각도, 고객, 환경, 기간, 출처(주기 조회/보고서), 검색.
- 행 클릭 → 사이드 시트: 이슈 요약, 발생 내역 타임라인(최근 50건), 대상 상세(키-값, **원시 JSON 금지**), 관련 보고서 링크, 상태 변경 이력(`insight_issue_event`), 메모 입력.
- 일괄 동작: 선택 확인, 선택 음소거, 선택 해결 처리.
- 상단 "지금 조회" 버튼(MSP 관리자, 마지막 실행 5분 이내면 비활성) → 즉시 sweep 1회.
- 고객 워크스페이스 개요 탭(T04)이 있으면 이 고객의 열린 이슈 목록을 추가. 없으면 생략하고 보고.

## 7. 알림 연동 (T02 알림함)
- 심각도 → 알림 분류: `CRITICAL → error`, `WARNING → warning`, `INFO → 알림 없음`. T02 규칙대로 error·warning 토스트는 자동 소멸하지 않습니다.
- 알림 시점: `source=SWEEP`으로 새 이슈 OPEN, 또는 재발(RESOLVED/STALE → OPEN).
- 같은 이슈 알림은 1시간 내 1회로 제한. MUTED 이슈는 알림 없음.
- sweep이 2회 연속 30% 이상 계정 실패 시 "알람 조회 장애" error 알림.

## 8. 상태 배지
`01-design-system.md` 5.2에 정의된 `kind="issue_state"`, `kind="severity"`, `kind="issue_source"`, `kind="resolved_reason"` 매핑을 사용합니다.

## 완료 조건
- [ ] sweep이 설정 주기로 실행되고, 알람/이벤트 API 외 다른 NCP API를 호출하지 않음(목킹으로 호출 대상 단언)
- [ ] 겹침 구간에서 같은 이벤트가 두 번 들어와도 occurrence 1건, 같은 시각 다른 Pod 이벤트는 2건으로 보존(UNIQUE + 테스트)
- [ ] 기존 `tests/test_insight_dashboard.py` 회귀 테스트 계속 통과(CronJob 묶기·보고서 중복 제거·계정 분리)
- [ ] 공식 확인 전 `NOT_SEEN` 자동 해결이 비활성임을 테스트로 확인
- [ ] 3절 상태 전이의 모든 경로 단위 테스트(시간 고정), 0절 결과에 따라 비활성화된 경로는 테스트에서 비활성 확인
- [ ] 7일 전 알람이 담긴 주간 보고서가 수집되어도 새 이슈·알림이 생기지 않음(4절)
- [ ] 대시보드 최상단에 현재 이슈·신선도·커버리지 표시, 조회 실패 시 경고
- [ ] 보고서를 만들지 않는 고객의 알람도 대시보드에 나타남(테스트 데이터로 증명)
- [ ] 원시 JSON 노출 0건, 단위 불명 지표에 임의 단위 표기 0건
- [ ] 알림 1시간 1회 제한·음소거 동작, 사이드바 "현재 이슈" 메뉴
- [ ] sweep 1회 소요 시간·호출 수 측정치(현재 16개 고객 기준), 기본 주기의 일일 NCP API 호출량 추정표 첨부

## 검증
- `python -m webapp.cli insight sweep --once --dry-run`: 대상 계정·조회 구간·예상 호출 수 출력(외부 호출 없음).
- `python -m webapp.cli insight sweep --once`는 테스트 환경에서 **사용자가 실행**하고 결과 요약을 받아 첨부합니다(Codex는 실제 NCP API를 호출하지 않음).
