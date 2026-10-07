# T06 — 스케줄링 고도화

> 선행: T05. 기준: `00-context.md` 6·11절. T00 2절(작업 실행 구조)·4절(기존 일정 테이블)을 반드시 참고해 **기존 스케줄러 위에서 확장**하세요.
> 스케줄러 엔진을 다른 것으로 교체하지 않습니다(교체가 필요하다고 판단되면 이유를 보고하고 멈추세요).
> 관리 명령 진입점은 `python -m webapp.cli`입니다(T00 확인).

## 현행 반영 (T00 결과·결정, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **활성 일정 테이블은 `control.account_report_schedules`** 입니다(id, tenant_id, cloud_account_id, report_type, **timezone**, run_hour, run_minute, **monthly_day**, **weekly_day**,
  enabled, next_run_at, last_enqueued_at, created_by). (account, type) unique, enabled 행 next_run_at 부분 인덱스. 구형 `report_schedules`는 scheduler가 읽지 않으므로 **쓰지 않습니다.**
- **실행 구조 유지**: `webapp/scheduler.py`가 일정 → `report_jobs`(QUEUED) 생성, `webapp/job_worker.py`가 `FOR UPDATE SKIP LOCKED`로 처리합니다.
- **재시도는 이미 있습니다**: 큐 재시도(`webapp/jobs.py:255`, `max_attempts=3`, 지연 최대 900초), stale 작업 재큐(360분), HTTP 재시도(`utils/common_rest.py:475`).
  일정별 `retry_max`·`retry_backoff_minutes` 컬럼을 만들지 말고 이 큐 재시도를 재사용·노출합니다(최종 실패 알림과 화면 표시만 추가).
- **동시성**: 전역 상한(`GLOBAL_MAX_RUNNING`)·계정당 1·Retry-After·HTTP 백오프 지터는 **T00B-8**에서 정의합니다. 이 작업은 그 값을 재사용하며 새 상한 변수를 만들지 않습니다.
  **일정 실행 분 분산**(`jitter_seconds`·`jitter_offset_seconds`)은 이 작업에서 정의합니다(HTTP 지터와 별개).
- **상태**: 작업 상태는 `QUEUED`이며 `PENDING`은 없습니다. `WAITING_DATA`는 **신규 상태**라 `report_jobs.status` CHECK 제약·claim 인덱스 조건·템플릿·필터·알림·기존 데이터 호환 변경이 필요합니다.
  계획에서 별도 승인받습니다.
- **`BILLING_FINALIZED`**: NCP 청구 데이터의 확정 시점 의미가 **공식 문서로 확인되지 않았습니다**(current-map 8.2). 확인 전에는 정책 값과 UI 자리만 두고 **선택 불가(비활성)** 로 하며,
  확인 방법(문서 위치·볼 필드)을 보고합니다. 사용자가 확인 결과를 주면 활성화합니다.
- **메일**: `email_recipients`·`email_deliveries` 테이블과 `python main.py --send-email` CLI 발송은 있으나 **예약 worker의 완료 후 메일 전달은 연결돼 있지 않습니다.**
  예약 전달은 신규 기능이므로, 이번 작업은 `DeliveryChannel` 인터페이스 + 알림함 알림(T02 승인 시)까지 하고 실제 메일 연결은 승인 후 진행합니다.
- **공유 링크**(`/s/{token}`)는 로그인 없는 **새 권한 경계**입니다. 이번 작업에서는 설계(토큰·만료·폐기·열람 범위·감사·레이트 제한·CSP)만 계획에 제시하고 **구현은 사용자 승인 후** 합니다.
- **시간대**: `timezone` 컬럼이 이미 있으므로 추가하지 않고, 값과 화면 입력은 `Asia/Seoul` 고정입니다.
- **지터 용량 초과**: 같은 기준 시각 그룹이 `3 × (jitter_seconds / 60)`개를 넘으면 분당 3개 상한을 지킬 수 없습니다. 이 경우의 처리를 계획에 명시하세요
  (권장: 무한 순환 없이 가장 적은 분에 배정하고 일정 화면·타임라인에 경고).

## 현재 문제 (2026-10-01 실측)
- 일정 8개 전부 `일일 · 매일 09:00 KST`. 고객 16곳 중 8곳 미자동화, 주간·월간 0개.
- 모든 일정이 같은 분에 실행 → NCP API 호출 집중.
- 월간은 1–28일만 가능(말일 불가). 실패 재시도는 큐에 있으나 화면에 보이지 않고, 데이터 준비 대기·완료 후 전달은 없음.
- 일정 화면에서 "다음 14일 동안 무엇이 언제 돌아가는지" 볼 수 없음.

## 데이터 모델

기존 일정 테이블 `control.account_report_schedules`의 컬럼에 **먼저 매핑**하고, 없는 것만 추가형 마이그레이션으로 더합니다. 기존 이름을 유지하세요.

| 개념 | 컬럼(없으면 추가) | 규칙 |
|---|---|---|
| 보고서 유형 | `report_type` | `00-context.md` 11절 열거형 (`DAILY`·`WEEKLY`·`MONTHLY`) |
| 요일 | `weekly_day` (기존) | ISO 8601: 1=월 … 7=일 (기존 폼 값과 동일) |
| 월 실행일 | `monthly_day` (기존) | 현행 1–28 → 1–28 또는 **-1 = 말일**(CHECK 제약 변경은 추가형 마이그레이션, 기존 값 유지) |
| 실행 시각·시간대 | `run_hour`, `run_minute`, `timezone` (기존) | `timezone` 값은 `Asia/Seoul` 유지 |
| 프로필 | `profile_id` (nullable) | null이면 `customer_report_config` 해석 결과 사용 |
| 지터 | `jitter_seconds` (int, 0–1800) | **신규 일정 기본 600, 기존 일정은 마이그레이션 시 0** |
| 지터 오프셋 | `jitter_offset_seconds` (int) | 저장값. 아래 알고리즘으로 생성 시·설정 변경 시에만 계산 |
| 데이터 준비 | `data_ready_policy` (`NONE` / `BILLING_FINALIZED`) | 월간만. `BILLING_FINALIZED`는 공식 확인 전 선택 불가 |
| 준비 재확인 | `data_ready_check_minutes` (기본 360), `data_ready_max_days` (기본 5) | |
| 재시도 | (추가하지 않음) | 기존 큐 재시도(`report_jobs.attempt_count`/`max_attempts`=3, `webapp/jobs.py:255`) 재사용 |
| 전달 | `delivery` (jsonb: `recipients[]`, `attach_pdf`, `share_link_days`) | 전달 설정은 **일정에만** 둡니다(프로필에는 없음). 메일 연결·공유 링크는 승인 후 |
| 활성 | `enabled` + `paused_reason`, `paused_by`, `paused_at` | 화면 상태는 `schedule_state()` 헬퍼로 `ACTIVE`/`PAUSED` |
| 다음 실행 | `next_run_at` (기존) | `compute_next_run()` 결과 저장 |
| 최근 결과 | (가능하면 추가하지 않음) | `report_jobs.schedule_id`로 최근 작업을 조회. 성능상 필요할 때만 컬럼 추가 |

### 다음 실행 계산
`compute_next_run(schedule, now) -> datetime` 하나로 통일합니다. 말일(-1)·윤년·월 길이 처리, 결과는 KST aware datetime.
기준 시각에 `jitter_offset_seconds`를 더한 값이 실제 실행 시각입니다.

### 지터 오프셋 알고리즘 (결정적)
```
if jitter_seconds == 0: offset = 0
else:
  base = int(sha256(f"{account_id}:{report_type}").hexdigest()[:8], 16) % jitter_seconds
  # 같은 기준 시각(run_hour:run_minute)을 가진 일정끼리 분 단위 슬롯을 배정해 한 분에 최대 3개
  slot_minute = base // 60
  같은 기준 시각 그룹을 account_id 오름차순으로 순회하며, slot_minute에 이미 3개가 있으면
  다음 분으로 이동(범위 끝에 닿으면 처음으로 돌아가되 한 바퀴만 확인)
  한 바퀴 돌아도 모든 분이 3개 이상이면(용량 초과) 가장 적은 분에 배정하고 over_capacity 경고 표시
  → offset = slot_minute*60 + base%60
```
- Python 내장 `hash()`는 프로세스마다 값이 바뀌므로 **사용 금지**.
- 화면 표시: `매일 09:00 · 실제 09:07`.

### 실행 정책
- **동시 실행 제한**: T00B-8의 전역 상한(`GLOBAL_MAX_RUNNING`)·계정당 1·Retry-After·HTTP 백오프 지터를 재사용합니다(새 상한 변수 금지). 일정 분 분산은 위 지터 알고리즘.
- **재시도**: 기존 큐 재시도를 그대로 씁니다. 화면에 시도 횟수(`attempt_count`/`max_attempts`)와 다음 시도 시각을 보여주고,
  최종 실패 시 알림함 `error` 알림(T02 알림함 승인 시) + 고객 워크스페이스 자동화 탭 빨간 표시.
- **데이터 준비 대기 `BILLING_FINALIZED`** (공식 확인 + `WAITING_DATA` 승인 후 활성화): 월간 실행 시 확정 청구 데이터가 아직 없으면 작업 상태를 `WAITING_DATA`로 두고
  `data_ready_check_minutes`마다 재확인, `data_ready_max_days`를 넘기면 추정 데이터로 생성하고 보고서에 "확정 청구 미반영" 표시.
  확정 여부 판단 방법은 코드 추정으로 정하지 않고, 공식 문서로 확인된 기준만 씁니다(current-map 8.2).
  - "추정으로 먼저 발행하고 확정 후 새 버전 생성"은 **T07**에서 구현합니다(버전 체계 필요).
- **전달**: 예약 worker의 완료 후 메일은 현재 연결돼 있지 않습니다(CLI `--send-email`만 있음). 이번 작업에서는 `DeliveryChannel` 인터페이스와 알림함 알림만 구현하고,
  기존 `email_recipients`·`email_deliveries`를 쓰는 메일 연결은 승인 후 진행합니다.

### 공유 링크 (이번 작업에서는 설계만 — 구현은 사용자 승인 후, T08 뷰어에서도 사용)
```
report_share_link
  id · token_hash (sha256, 원문 토큰은 저장하지 않음) · report_id · report_version_id (nullable, T07 이후 사용)
  expires_at · created_by · created_at · revoked_at · revoked_by · last_accessed_at · access_count
```
- 라우트 `GET /s/{token}` — 로그인 없이 해당 보고서 1건의 본문만 열람(앱 셸·다른 보고서 링크 없음), 만료·폐기 시 410.
- 기본 만료 14일(`SHARE_LINK_DEFAULT_DAYS`), 최대 90일. 일정 `delivery.share_link_days`가 있으면 그 값.
- 뷰어에서 "공유 링크 만들기"(외부용, 만료일 선택)와 "주소 복사"(내부 URL)는 **별개의 동작**입니다. 발급된 링크 목록·폐기는 뷰어 출처 패널에서.

## 화면

### `/msp/schedules` 실행 일정
- 상단 요약: `활성 일정 8 · 미자동화 고객 8 · 오늘 실행 예정 8 · 최근 24시간 실패 0` (각각 필터 링크).
- 보기 전환: **목록**(T03 패턴) / **타임라인**(다음 14일, 행 = 계정, 열 = 날짜, 칸 = 실행 예정 점·유형별 모양·시각 툴팁).
  같은 분에 4개 이상 몰리면 타임라인에 겹침 경고.
- **미자동화 고객** 섹션: 일정이 하나도 없는 고객·계정 목록 + "일정 만들기" 버튼(일괄 마법사로 대상 선택된 채 이동).
- 일괄 등록은 사이드 시트 마법사: ① 대상 계정 선택 → ② 유형·주기·시각·지터 → ③ 프로필 → ④ 데이터 준비·전달(승인된 항목만) → ⑤ 확인(생성/갱신될 일정 수, 다음 실행 미리보기).
  **기존 `POST /msp/schedules/bulk` 라우트와 폼은 유지**합니다(JS 없을 때 대체 수단, 마법사도 최종 제출은 이 라우트로).
- 행 동작 `⋯`: 편집, 지금 실행, 중지(사유 입력)·재개, 삭제(확인 대화상자). 일정 삭제는 `⋯` 메뉴에 둬도 됩니다(되돌릴 수 있는 설정이므로).

### 고객 워크스페이스 › 자동화 탭 (T04)
- 위 일정 편집 시트를 재사용. 계정별로 일·주·월 3행 고정 표시(없으면 "일정 없음 · 추가").

### 통합 대시보드
- "오늘 실행" 위젯: 예정 / 완료 / 부분 수집 / 실패 / 데이터 대기 개수 + 실패 목록 링크.

## 완료 조건
- [ ] `compute_next_run` 테스트: 매일·매주·매월·말일(2·4·12월, 윤년 2월)·연말 경계
- [ ] 지터 오프셋이 프로세스를 재시작해도 동일, `jitter_seconds=0`이면 0, 신규 기본 설정에서 같은 분 실행 일정 ≤ 3개
- [ ] 기존 일정 전부가 마이그레이션 후 **같은 실제 실행 시각**(지터 0)과 같은 상태로 유지, 마이그레이션 빈 DB 2회 적용 성공
- [ ] 기존 큐 재시도 경로에서 시도 횟수 표시·최종 실패 알림 시나리오 테스트(외부 API 목킹)
- [ ] `BILLING_FINALIZED` 미확인 상태에서 선택 불가 테스트. (공식 확인·`WAITING_DATA` 승인 시) 대기 → 재확인 → 확정 시 생성 / 최대 대기 초과 시 추정 생성 시나리오 테스트
- [ ] 공유 링크 설계안 제출. (승인 후 구현 시) 발급·열람·만료(410)·폐기 테스트, 토큰 원문 미저장 확인
- [ ] 지터 용량 초과 그룹에서 무한 순환 없이 배정되고 경고가 표시됨
- [ ] 타임라인 보기: 375px에서는 타임라인 영역 안에서만 가로 스크롤, 1440px에서 14일이 한 화면
- [ ] 미자동화 고객 목록이 실제 데이터와 일치(현재 8곳)
- [ ] `schedule_state()`가 `status_badge`(01-design-system.md 5.2)를 통해 표시됨

## 검증
- `python -m webapp.cli schedules simulate --days 14` 명령을 추가해 다음 14일 실행 계획(실제 시각 포함)을 텍스트로 출력, 결과 첨부.
