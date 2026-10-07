# 현행 구조 지도 (2026-10-06, 8d2e31062282e6b629b5508452ba83df67892e54)

조사 기준: 로컬 작업 트리 및 위 커밋. 선행 자료는 AGENTS.md(특히 6절), docs/reviews/2026-10-06-code-review.html, docs/redesign/00-context.md, 01-design-system.md, T00·T00A·T00B·T01–T10이다. 기존 리뷰를 코드와 대조·보완했으며, 이번 산출물은 이 문서 하나다. 코드 수정·DB 접속·마이그레이션·배포·커밋은 하지 않는다.

인터넷은 사용하지 않았다. 공식 NCP 계약, 실제 배포 이미지·DB 내용·운영 PVC는 **미확인**이다. 문서에 있는 예전 배포 정보나 측정값을 현재 운영 환경에서 재검증한 결과로 취급하지 않는다. deploy/private/, secrets/, .env*는 조사 대상에서 제외했다. 환경변수는 이름만 기록한다.

## 1. 스택 요약

### 1.1 실제 스택과 기존 자료 대조

| 항목 | 현행 확인 결과 | 근거 |
|---|---|---|
| 언어 | Python 3.13 계열. 조사 PC의 기본 Python 및 기존 가상환경 실행 버전은 모두 **3.13.14** | python --version, .venv 실행 파일의 버전 |
| 웹 | Flask 3, gunicorn, 서버 렌더링 | webapp/app.py:35, webapp/wsgi.py, Dockerfile.runtime |
| 템플릿·브라우저 | 포털은 Jinja2 + 바닐라 JS. 보고서 본문은 별도의 Python HTML 렌더러 | webapp/templates/, webapp/static/, app/renderers/html_renderer.py:709 |
| DB 접근 | psycopg 3 + 원시 SQL. ORM 없음 | database/report_repository.py, webapp/repository.py, webapp/jobs.py |
| DB | PostgreSQL 16 이미지; control + public_data/gov_data + audit | 배포 정의, database/schema/ |
| 마이그레이션 | 번호순 SQL 22개(000–210), 자체 셸 스크립트, forward-only | deploy/docker/migrate.sh |
| 작업 처리 | DB 큐 + 자체 scheduler/worker 루프. Celery/RQ/APScheduler 아님 | webapp/scheduler.py, webapp/job_worker.py |
| 테스트 | pytest, 일부 테스트에서 Node로 브라우저 스크립트 동작 검사 | requirements-dev.txt, tests/ |
| 린터·포매터·잠금 | 현재 추적 파일에서 pyproject.toml, pytest.ini, setup.cfg, tox.ini, .editorconfig, .gitattributes, 의존성 잠금 파일 없음 | Git 파일 목록 |

AGENTS.md 6절의 구조 설명은 코드와 일치한다. 기존 리뷰의 추적 파일 256개와 달리 현재는 273개이며, 문서 기준점 커밋에 추가된 17개 파일 차이다. 리뷰의 커버리지 73.8%, DB 성능·스냅샷 크기·취약점 수치는 **기존 측정값**이며 이번에 재측정하지 않았다.

requirements.txt는 정확한 버전 잠금이 아니라 범위다: requests >=2.31,<3; python-dateutil >=2.8.2,<3; python-dotenv >=1,<2; psycopg[binary] >=3.2,<4; Flask >=3.1,<4; gunicorn >=23,<24; argon2-cffi >=23.1,<26; cryptography >=44,<46; tzdata >=2024.1. 개발 의존성은 pytest >=9,<10이다.

기존 .venv의 설치 메타데이터: Flask 3.1.3, Jinja2 3.1.6, psycopg 3.3.4, requests 2.32.5, python-dotenv 1.2.1, pytest 9.1.1, cryptography 45.0.7, argon2-cffi 25.1.0. 이는 로컬 환경 값이지 운영 이미지의 설치 버전 확인 결과가 아니다.

### 1.2 작업 트리 및 줄바꿈 보존

- 기준 HEAD: `8d2e31062282e6b629b5508452ba83df67892e54`, 메시지 `docs: checkpoint project guidance and redesign plans`.
- 조사 시작 시 추적 파일의 수정 표시는 **0개**였다. 기존 리뷰에 기록된 “CRLF 차이로 41개 수정”과 시점 차이가 있다.
- `git ls-files --eol` 기준 작업 트리에 w/crlf 4개, w/mixed 37개가 있다. 이 41개는 현재 Git 수정 상태라는 뜻이 아니다. 줄바꿈은 그대로 보존한다.
- 기존 미추적 파일: `ClaMax _ 메일.pdf`, `architect-clabi-uiux-audit.html`, `모니터링 report 바라는 점 관련 파일.docx`. 삭제·스테이징하지 않는다.
- 읽기 금지 경로를 제외한 추적 파일 269개의 SHA-256을 작업 전 기록했다. 문서 추가 후 비교하여 기존 파일 변경 여부를 확인한다.
- restore, stash, checkout, reset, 줄바꿈 정규화, 기존 파일 재저장을 수행하지 않는다.

### 1.3 테스트 실행 결과와 검증 한계

테스트 실행 명령은 요청대로 **`python -m pytest -q`만** 사용했다.

| 실행 환경 | 결과 |
|---|---|
| 기본 Python 3.13.14 | 실패: No module named pytest, 종료 코드 1 |
| 기존 .venv를 해당 프로세스 PATH 앞에 지정한 Python 3.13.14 | **620 passed, 5 skipped, 204 subtests passed in 7.74s**, 종료 코드 0 |

의존성을 설치하지 않았다. 자동 load_dotenv를 억제하도록 테스트 프로세스에 PYTHON_DOTENV_DISABLED=1을 사용했다. REPORT_DB_INTEGRATION_TEST, REPORT_DB_WORKER_INTEGRATION_TEST 등 DB 연결 활성화 변수를 설정하지 않았다.

5개 skip은 tests/test_database_integration.py의 1개, tests/test_portal_integration.py의 3개, tests/test_worker_persistence_integration.py의 1개이며 기존 DB 통합 테스트 opt-in 조건에 따른다. Node는 로컬에 있어 해당 스크립트 테스트들은 실행됐다. 테스트 파일은 38개다. 수집기·정규화·분석·보고서 렌더링·포털 권한/라우트·일정·알람 묶기·파일 정리 등을 기존 테스트로 검사했다.

새 테스트는 없다(실행 코드 변경 없음). 커버리지, 린터·포매터, 이미지 빌드, 취약점 조회, DB 마이그레이션, 운영 접속은 실행하지 않았다. 화면을 변경하지 않았으므로 4개 폭·라이트/다크·키보드 UI 검증도 이번 실행 결과로 주장하지 않는다.

### 1.4 빌드·배포 식별

- 런타임/마이그레이션 Dockerfile과 루트 Dockerfile이 함께 있다. Python 3.13-slim 기반이며 버전 범위 설치라 동일 소스만으로 동일 패키지 집합을 보장하지 않는다.
- deploy/scripts/run-sourcebuild.ps1의 Resolve-SourceBuildTag 및 빌드 성공 이력 집계가 build-N 태그를 만든다.
- deploy/scripts/deploy-sourcebuild-images.ps1은 이미지 태그와 전체 소스 리비전을 확인하여 Helm image.tag/sourceRevision에 전달한다. atomic/wait 배포 경로가 있다. 이번에는 실행하지 않았다.
- Helm deployments.yaml의 APP_VERSION, APP_SOURCE_REVISION → webapp/app.py 설정 → presentation 컨텍스트 → base.html 푸터의 버전·짧은 커밋 표기다. 별도 SourceDeploy 정의도 저장소에 있다.
- `build-46 · d222302`는 기존 문서의 배포 기록이다. 현재 운영 이미지·Helm 리비전과의 일치는 **미확인**이다.
- migrate.sh는 schema_versions만 보고 후속 SQL을 건너뛰는 도구가 아니라 번호순 SQL 파일을 적용한다. 신규 SQL의 재실행 안전성이 중요하다. 현재 마지막 스키마 번호는 210이다.

## 2. 프로세스·작업 실행 구조 (다이어그램)

```text
브라우저 → gunicorn(webapp.wsgi:app, 컨테이너 기본 2 workers × 4 threads)
               ├─ PortalRepository → 포털 조회·관리
               └─ POST 즉시 생성 → ReportJobRepository.enqueue
                                           │
scheduler 자체 루프(기본 30초) ──────────────┤
  ├─ 만료된 작업 잠금 재큐잉                 ↓
  └─ account_report_schedules → control.report_jobs
                                           │ FOR UPDATE SKIP LOCKED
                   ┌───────────────────────┴───────────────────────┐
             public job_worker                               gov job_worker
             환경 전용 DB 역할                               환경 전용 DB 역할
                   └──────────── ReportRunner ──────────────────────┘
                                      ├─ NCP 수집·분석·HTML/JSON
                                      └─ 환경별 DB 스냅샷·상세 데이터

별도 Kubernetes CronJob
  ├─ artifact_cleanup: 정리 요청·보존 정책·파일 삭제 재시도(기본 5분)
  └─ DB 백업: 보고서 일정 실행기가 아님
```

- webapp/scheduler.py:15: 자체 반복 루프이며 최소 폴링 간격은 5초다. due 일정은 jobs.py:144에서 잠그고 최대 100개 처리한다. 과거 일/주/월을 대상으로 작업을 넣고 next_run_at을 갱신한다.
- webapp/jobs.py:194: QUEUED·실행 가능 시각·남은 시도 횟수 조건으로 1개 claim, RUNNING 전환과 잠금·시작 시각·attempt_count 갱신을 한 트랜잭션에서 한다.
- webapp/job_worker.py:24,64: 프로세스당 순차 1작업. public/gov 역할을 검사하고 암호화된 계정 자격증명을 로드한다. API factory는 작업 종료 시 닫는다. 기본 폴링 5초(최소 2초).
- 큐 재시도는 이미 있다(jobs.py:255): 기본 max_attempts=3, 지수 지연 상한 900초. 장기 RUNNING은 requeue_stale(:221)의 기본 360분 기준으로 재큐잉/실패 처리한다. 작업 하트비트는 없다.
- HTTP 재시도도 이미 있다(utils/common_rest.py:475): 안전한 읽기 요청의 연결/timeout·429·5xx 재시도, 기본 3회 설정, 지수 대기. 지터·Retry-After 준수 및 connect/read 타임아웃 분리는 현행 구현과 구별해야 한다.
- Helm 기본 각 역할 replica=1이다. worker를 늘리면 SKIP LOCKED로 claim은 분산되지만 전체 환경/계정 공통 동시성 상한은 없다. worker별 슬롯 3개는 전역 동시성 3개와 다르다.
- 이력의 **Scheduler는 사용자 계정명이 아니라** history.html:12의 requested_by_name 누락 시 대체 문구다. 예약 작업은 requested_by=NULL로 넣는다. 다른 이유로 요청자 이름이 없는 작업에도 이 문구가 나올 수 있다.
- main.py CLI의 직접 생성·메일 발송과 webapp.worker의 단발 실행 경로도 남아 있다. 예약 실행의 실제 진입점은 webapp.job_worker다.

## 3. 라우트 표

표의 핸들러 앞 파일은 각각 webapp/auth_routes.py, msp_routes.py, portal_routes.py이다. 명시적 라우트 38개(로그인 GET/POST를 나누면 메서드·경로 쌍 39개)와 Flask 정적 파일 라우트가 있다.

권한 표기:

- **로그인/고객 범위**: 고객 memberships 또는 MSP 환경 범위 검사. CUSTOMER_VIEWER도 즉시 생성은 현재 허용된다.
- **MSP**: MSP_ADMIN, MSP_OPERATOR, SYSTEM_ADMIN + 환경 범위. SECURITY_AUDITOR는 이 집합에 없다.
- **관리자**: _msp_admin_required의 **MSP_ADMIN** + 관리 가능한 환경. SYSTEM_ADMIN 이름만으로 이 검사에 통과하지 않는다.
- **고객 관리**: 범위 내 MSP_ADMIN 또는 해당 고객의 CUSTOMER_ADMIN.
- POST는 공통 CSRF 검증 대상이며 로그인은 별도 로그인 CSRF 절차가 있다. “→”는 폼 처리 후 리다이렉트를 뜻한다.

### 3.1 인증·공통

| 메서드·경로 | 핸들러 | 화면/응답 | 권한 |
|---|---|---|---|
| GET /health/live | auth_routes.py:47 health_live | JSON | 공개 |
| GET /health/ready | :51 health_ready | JSON, DB readiness 조회 | 공개 |
| GET, POST /login | :56 login | login.html 또는 → 기본 화면 | 공개; 인증된 GET은 이미 리다이렉트 |
| POST /logout | :118 logout | → 로그인 | 로그인 |
| GET / | :127 index | → /msp 또는 /portal | 로그인 |
| GET /static/<path:filename> | Flask static | 정적 파일 | 공개; 현재 공통 요청 훅 영향은 있음 |

### 3.2 MSP

| 메서드·경로 | msp_routes.py 핸들러 | 화면/응답 | 권한 |
|---|---|---|---|
| GET /msp | :74 msp_dashboard | msp_dashboard.html | MSP |
| GET /msp/data-cleanup | :82 msp_data_cleanup | data_cleanup.html | 관리자 |
| POST /msp/data-cleanup | :108 run_data_cleanup | 정리 요청 저장 → 목록 | 관리자, 대상·확인 문구 검사 |
| GET /msp/customers/<environment> | :158 msp_customers | customers.html | MSP, public/gov 범위 |
| GET /msp/schedules | :174 msp_schedules | schedules.html | MSP |
| POST /msp/report-retention/bulk | :190 bulk_report_retention | → 일정 화면 | 관리자 |
| GET /msp/users | :223 msp_users | users.html | 관리자 |
| POST /msp/users | :236 create_portal_user | → 사용자 화면 | 관리자 |
| POST /msp/users/platform | :258 create_msp_user | → 사용자 화면 | 관리자 |
| POST /msp/users/platform/<user_id>/enabled | :284 set_msp_user_enabled | → 사용자 화면 | 관리자 |
| POST /msp/users/<user_id>/delete | :311 delete_user_account | → 사용자 화면 | 관리자 |
| POST /msp/users/memberships | :337 assign_portal_user | → 사용자 화면 | 관리자, 고객 관리 범위 |
| POST /msp/schedules/<schedule_id>/enabled | :362 set_schedule_enabled | → 일정 화면 | 관리자 |
| POST /msp/schedules/bulk | :376 bulk_schedules | 일정 생성/삭제 → 목록 | 관리자 |
| POST /msp/customers/<environment> | :432 create_customer | → 고객 화면 | 관리자 |
| GET /msp/customer/<tenant_id> | :456 msp_customer | customer_detail.html | MSP, 고객 접근 범위 |
| POST /msp/customer/<tenant_id>/report-settings | :488 update_customer_report_settings | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/logo | :540 update_customer_logo | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/logo/delete | :570 delete_customer_logo | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/credentials | :584 register_credential | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/credentials/<account_id>/delete | :606 delete_credential | → 고객 화면 | 관리자, 계정 코드 확인 |
| POST /msp/customer/<tenant_id>/delete | :636 delete_customer | 오프보딩 → 목록 | 관리자 |
| POST /msp/customer/<tenant_id>/reactivate | :660 reactivate_customer | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/anonymize | :684 anonymize_customer | → 고객 화면 | 관리자 |
| POST /msp/customer/<tenant_id>/permanent-delete | :709 permanently_delete_customer | → 목록 | 관리자, 파괴적 처리 확인 |

### 3.3 고객·보고서·이력

| 메서드·경로 | portal_routes.py 핸들러 | 화면/응답 | 권한 |
|---|---|---|---|
| POST /accounts/<account_id>/report-jobs | :52 enqueue_report | → 고객/포털 화면 | 로그인 + 해당 고객 접근 |
| POST /accounts/<account_id>/schedules | :77 save_schedule | → 고객/포털 화면 | 고객 관리 |
| GET /portal | :108 customer_portal | customer_portal.html | 로그인 + 고객 범위 |
| GET /reports/<report_id> | :154 report_detail | report_detail.html | 로그인 + 고객 범위 |
| POST /reports/<report_id>/delete | :172 delete_report | → 포털 | **MSP 운영자 포함**, 고객 범위 |
| GET /history | :198 report_history | history.html | 로그인 + 고객 범위 |
| GET /notifications | :234 notifications | JSON | 로그인 + 고객 범위 |
| GET /reports/<report_id>/content | :285 report_content | 저장된 HTML 파일 | 로그인 + 고객 범위, 경로·크기·해시 검사 |

역할·테넌트 판정은 webapp/route_access.py:20,33,46,111,122에 있다. ID 경로는 현재 문자열이며 UUID converter 전환은 후속 변경이다. 새 워크스페이스 7탭·프로필·독립 현재 이슈·재렌더/검증 라우트는 아직 없다. 기존 URL은 이후에도 보존해야 한다.

## 4. 데이터 모델 (ERD 텍스트)

### 4.1 관계와 격리

```text
control.tenants
  ├─< cloud_accounts ── encrypted_credentials
  │      ├─< account_report_schedules ──< report_jobs
  │      └─< report_jobs ──(완료 시)──> report_runs
  ├─< memberships >─ users ─< platform_roles
  │                                └─< user_sessions
  ├── tenant_report_settings (출력 설정 + 보존 정책 JSON)
  ├── tenant_branding (로고 바이트)
  └─< report_runs
          ├─< report_artifacts / collection_errors              [control]
          ├── report_snapshots / network_configuration_snapshots [환경별]
          ├─< metric_series / metric_summaries / insight_events  [환경별]
          └─< activity_events / cost_details / billing_*        [환경별]

report_runs ──> daily_customer_facts / daily_account_facts 최신 참조
분석 결과 ──> control.event_cases / policy_exceptions
삭제 요청 ──> report_runs.cleanup_* ──> artifact_cleanup_outbox
감사 기록 ──> audit.authentication_logs / data_change_logs 등
```

control은 공유 메타데이터, public_data/gov_data는 같은 구조의 환경별 수집 데이터다. 역할별 DB 계정과 RLS/FORCE RLS를 사용한다. 파이프라인 저장 시 트랜잭션에 tenant/environment 컨텍스트를 설정한다(database/report_repository.py:44). MSP 조회는 애플리케이션의 환경·고객 범위 검사도 중요하다. “RLS가 모든 MSP 환경 범위를 자동 제한한다”라고 가정하면 안 된다.

아래 필드는 현재 정의를 합친 요약이다. 공통 created_at/updated_at을 C/U로 줄여 썼다. 모든 보조 fact 테이블의 전체 DDL을 복제하지 않고, T00에서 요구한 고객·계정·키·사용자·일정·작업·보고서·설정·알림의 필드와 주요 키를 중심으로 기록한다. 정확한 제약은 database/schema/의 번호순 SQL이 기준이다.

### 4.2 control 주요 테이블

| 테이블 | 필드 | 관계·인덱스/제약 |
|---|---|---|
| tenants | id, customer_code, customer_name, environment, region, timezone, worker_group, status, primary_contact_email, metadata, C/U | PK id; customer_code unique; (id, environment) unique |
| users | id, email, password_hash, display_name, status, mfa_enabled, external_identity_provider, external_subject, last_login_at, C/U | lower(email) unique; 외부 identity 부분 unique |
| memberships | id, tenant_id, user_id, role, status, C/U | tenant/user FK; (tenant_id,user_id) unique |
| platform_roles | id, user_id, role, environment_scope, created_at | user FK; 사용자·역할·환경 범위 unique |
| cloud_accounts | id, tenant_id, account_code, display_name, environment, region, status, C/U | (tenant_id,account_code), (id,tenant_id) unique; 고객·환경 복합 FK |
| encrypted_credentials | id, tenant_id, cloud_account_id, provider, key_reference, algorithm, encrypted_dek, dek_nonce, ciphertext, credential_nonce, access_key_hint, credential_version, status, last_verified_at, rotated_at, C/U | 계정당 1행; (account,tenant) FK, CASCADE. 필드 이름만 조사 |
| credential_refs | id, tenant_id, provider, secret_reference, access_key_hint, status, last_verified_at, last_rotated_at, expires_at, C/U | 구형 고객 단위 자격증명 참조. 현재 포털 암호화 계정 키와 별개 |
| user_sessions | id, user_id, token_hash, csrf_token_hash, expires_at, last_seen_at, created_at | token_hash unique; user/expiry 인덱스 |
| account_report_schedules | id, tenant_id, cloud_account_id, report_type, timezone, run_hour, run_minute, monthly_day, weekly_day, enabled, next_run_at, last_enqueued_at, created_by, C/U | **실제 일정 테이블**. (account,type) unique; enabled 행 next_run_at 부분 인덱스 |
| report_schedules | id, tenant_id, report_type, cron_expression, timezone, enabled, recipient_mode, config, next_run_at, last_run_at, C/U | 구형 테이블, (tenant,type) unique. 현재 scheduler가 읽는 테이블 아님 |
| report_jobs | id, tenant_id, cloud_account_id, environment, report_type, target_value, period_key, trigger_type, requested_by, schedule_id, status, attempt_count, max_attempts, available_at, locked_at, locked_by, started_at, completed_at, report_run_id, last_error, C/U, period_start, period_end | QUEUED/RUNNING의 (account,type,period_key) 부분 unique; 환경·available_at·created_at claim 인덱스; 고객 이력 인덱스 |
| report_runs | id, tenant_id, environment, report_type, period_start, period_end, end_exclusive, status, trigger_type, requested_by, idempotency_key, collector_version, normalizer_version, renderer_version, cloud_account_id, attempt_count, error_count, queued_at, started_at, completed_at, C/U, cleanup_requested_at, cleanup_requested_by, cleanup_reason, cleanup_attempt_count, cleanup_next_attempt_at, cleanup_last_error_code | idempotency_key unique; run/tenant/environment 복합 unique; 고객·기간, 미완료 상태, cleanup_due 인덱스 |
| report_artifacts | id, report_run_id, tenant_id, artifact_type, storage_uri, content_type, byte_size, checksum_sha256, retention_until, created_at | (run,type,URI) unique; run/tenant FK CASCADE; 고객 생성 시각 인덱스 |
| tenant_report_settings | tenant_id, settings, updated_by, C/U | tenant PK. settings JSONB 한 행에 고객 출력 설정·보존 정책 저장 |
| tenant_branding | tenant_id, logo_content, logo_content_type, logo_width, logo_height, logo_sha256, updated_by, C/U | tenant PK. 실제 이미지 바이트 보관; 파일 시스템 로고 경로 모델 아님 |
| collection_errors | id, report_run_id, tenant_id, collector, stage, target_type, target_id, status_code, error_code, message, retryable, occurred_at | 보고서 및 고객·시각 인덱스 |
| artifact_cleanup_outbox | id, operation_id, tenant_id, storage_uri, expected_sha256, expected_byte_size, attempt_count, next_attempt_at, last_error_code, created_at | (operation,URI) unique; due 인덱스. 보고서 삭제 뒤에도 남도록 설계 |

관련 DDL: 020(control), 070(포털), 080(계정 일정·작업), 090(사용자 기간), 100(오프보딩), 110(테스트 고객 삭제 확장), 140(설정), 150(브랜딩), 180(분석), 190(정리 outbox), 200(주간), 210(정리 요청 큐).

tenant_report_settings.settings는 schema_version 1.4, sections, section_order, resource_categories, monitoring_categories, operational_analysis 등을 담는다. 보존은 같은 JSON의 retention_policies.DAILY/WEEKLY/MONTHLY에 mode=DAYS/FOREVER 및 days로 저장한다. 별도 보존 정책 테이블·계정별 프로필 버전 테이블은 없다. DAYS 범위는 1–3650이고 CUSTOM 별도 정책은 없다.

### 4.3 환경별 데이터와 분석·메일 보조 모델

| 테이블 | 핵심 필드·저장 의미 | 키·인덱스 |
|---|---|---|
| report_snapshots | id, report_run_id, tenant_id, environment, schema_version, collector/normalizer/renderer_version, normalized_data(JSONB), content_hash_sha256, created_at | 보고서당 1개; run/tenant/env FK CASCADE |
| network_configuration_snapshots | id, run/tenant/account/env, captured_at, period_start/end, end_exclusive, source, schema_version, configuration(JSON array), capture_metadata(JSON), content_hash_sha256, created_at | 보고서당 1개; tenant/account/captured_at DESC 조회 인덱스 |
| metric_series | id, run/tenant/env, resource_id/name, metric_group/name, dimensions, interval_name, aggregation, period_start/end, points(JSON), artifact_uri, point_count, created_at | 보고서·그룹 조회 인덱스; points에 시각·값 |
| metric_summaries | 보고서·자원·지표·차원과 min/avg/max/sample 요약 | 보고서별 지표 조회 |
| insight_events | id, run/tenant/env, source_event_id, occurred_at, ended_at, severity, service_name, resource_id/name/type, rule_id/name, metric, operator, criteria, detect_value, unit, aggregation, interval_name, notification_status, in_maintenance, resource_deleted, details(JSON), created_at | report_run_id **NOT NULL**; 고객·시각/심각도 인덱스, details GIN, (run,source_event_id,occurred_at) 부분 unique |
| activity_events | 보고서·테넌트·환경, 발생 시각, 계정/상품/자원, action/result, source_ip, details | 보고서 및 고객 시각 조회 |
| cost_details, billing_cost_facts, billing_account_cost_facts | 정규화 비용 행 및 조회 기간·금액 기준·할인·VAT·신뢰도 등 비교 근거 | 보고서·고객/계정·기간에 따른 조회 |
| raw_payload_refs | 보고서 관련 원본 데이터 URI 참조 | 파일 정리 대상 참조에도 포함 |

Route Table·ACG·NACL 규칙은 network_configuration_snapshots의 configuration에 별도 저장한다. 일반 report_snapshots만 있으면 모든 네트워크 렌더 입력이 복원된다고 가정하면 안 된다.

control.daily_customer_facts는 (tenant_id,fact_date), daily_account_facts는 (tenant_id,cloud_account_id,fact_date)가 기본 키이며 latest_report_run_id와 자원/이벤트/비용 요약을 가진다. control.event_cases에는 source_event_id, 상태·담당자·확인/해결 시각 외에 분석용 account/run/rule/resource/category/evidence/impact/recommendation/priority/first-last/count 필드가 이미 있다. 분석 이슈 이력이며 T09의 독립 Insight 현재 상태 저장소와 동일하지 않다. policy_exceptions도 존재한다.

audit.data_change_logs에는 actor, 대상 table/record, operation, changed_fields, request_id, occurred_at 등이 있다. 현재 설정 변경 감사 코드(webapp/repository.py:1842–1941)를 재사용할 수 있지만 완전한 before/after 이력이라고 보장할 수는 없다.

control.email_recipients에는 고객, 이메일, 표시명, daily/monthly/event 수신 여부, enabled가 있고 고객·이메일 unique이다. email_deliveries에는 보고서·수신자·provider/message_id·status·attempt/error·queued/sent 시각이 있다. **테이블 존재만으로 예약 worker의 이메일 전송 기능이 연결돼 있다는 뜻은 아니다.** 포털 notifications 전용 저장 테이블은 없다(8절).

## 5. 수집 → 분석 → 렌더 → 저장 흐름 (파일·함수 경로 포함)

### 5.1 실제 호출 순서와 수집 범위

주 진입은 webapp/job_worker.py:64 → APIFactory/ReportRunner.run(app/runner.py:2197)이다. main.py:419와 webapp/worker.py도 같은 runner를 사용한다.

1. 보고 기간·계정·고객 옵션을 만들고 build_collection_plan(app/report_pipeline.py:94)으로 목록 대상과 모니터링에 필요한 자원의 합집합을 정한다. LB 지표에는 TARGET_GROUP 등 추가 대상이 필요하다.
2. 인프라 스냅샷 사용 여부를 결정(app/runner.py:839), 실제 보고 기간 내 관측된 저장 스냅샷을 조회(database/report_repository.py:104)한다.
3. _collect_live_resource_state(app/runner.py:1946)로 현재 자원을 수집한다. 기간 스냅샷이 있어도 현재 백업 수집 경로는 별도로 남는다.
4. _collect_network_configuration_snapshot(:660)에서 Route Table/ACG/NACL을 재사용하거나 별도 수집한다. 재사용 조건(:691)은 LIVE_API_COLLECTION 및 범주 충족 여부를 본다.
5. observability(:1073): 서버 지표 → 인프라 지표 → Insight 이벤트 → 활동 이력 → 선택된 WMS → 선택된 Security Monitoring 순서다.
6. billing(:1406): 조직·계정 범위와 청구 자료를 수집·정규화하고 baseline(:1277)을 조회한다.
7. ReportResult(:2466)를 만들고 generated_at을 넣은 뒤 결정적 분석(:2498), HTML/JSON 생성·DB 저장(:1496)을 수행한다.

옵션에 따라 단계와 API가 생략된다. 아래는 호출 경로의 순서이지 모든 보고서가 모든 API를 반드시 호출한다는 뜻이 아니다.

| 단계 | 클라이언트 호출·순서 | 코드 위치 |
|---|---|---|
| 서버 | get_server_instance_list → get_network_interface_instance_list → get_block_storage_instance_list; 목록 페이지 처리 | collectors/servercollector.py:59 |
| 네트워크 인벤토리 | get_vpc_list → get_subnet_list → get_route_table_list 및 연결 subnet/route → get_access_control_group_list 및 rule → get_network_acl_list 및 rule → NAT Gateway → Peering → Public IP | collectors/infrastructurecollector.py:186–394 |
| 플랫폼 | Block Storage Snapshot → Server Image → Global DNS → Certificate 목록 | infrastructurecollector.py:395–483 |
| 서비스 | Load Balancer → Target Group/Target → NAS → MySQL/PostgreSQL/MSSQL/MongoDB/Redis 계열 → NKS | infrastructurecollector.py:484–625 |
| 보충 인벤토리 | Resource Manager get_resource_list 후 정규화·병합 | infrastructurecollector.py:626,1107 |
| 서버 지표 | Cloud Insight 상품/지표 확인 → 파일시스템 지표 식별 → multiple query를 지표·시간 구간·집계별로 분할 | collectors/insightmetriccollector.py:64,317,553,611 |
| 인프라 지표 | 수집 자원 유형에 대응하는 지표 카탈로그로 조회 | app/runner.py:1073의 인프라 지표 경로 |
| Insight 이벤트 | POST /cw_fea/real/cw/api/event/search, 페이지별 조회 | app/runner.py:1125, ncp_api/cloudinsightAPI.py:109 |
| 활동 이력 | get_activity_list | app/runner.py:1140 |
| WMS·보안 | WMS monitor/result 및 Anti-Virus/DDoS/IDS/IPS/WAF 목록 | app/runner.py:1155,1188; 옵션으로 제어 |
| 비용 | 조직·계정 → demand cost → product demand → contract demand → daily usage → 선택적 MTD → contract usage → price/product price → 확정 월 보충 → 할인·크레딧·코인 내역 | app/runner.py:1406, collectors/billingcollector.py:64–214,394 |

Resource Manager에서 BACKUP 관련 자원이 보이는 것과 전용 Backup 서비스의 서버별 경로·보관일·용량을 수집하는 것은 다르다. 후자는 현재 전용 구현·공식 API 지원을 동일시하지 않으며 공식 지원 여부는 미확인이다.

### 5.2 스냅샷과 실제 저장 내용

- 일반 스냅샷은 ReportResult.to_persistence_dict(app/report_models.py:377)의 정규화 데이터이며, 보고서별 DB JSONB로 저장한다. public JSON과 내부 저장 JSON은 같지 않다.
- database/report_repository.py:632는 server_metrics에 raw 응답을 포함한 내부 지표를 보관한다. raw.dps에는 시각·값 쌍이 있다.
- 목록용 infrastructure 외에 infrastructure_snapshot 및 관측 시각/출처 metadata가 있다. runner.py:2027 부근은 과거 기간 표시용 필터 전 현재 인프라를 별도로 백업한다.
- 기간 조회는 단순 “보고서를 생성했는가”가 아니라 **해당 기간에 실제 관측된 스냅샷인가**를 검사한다. 현재 상태를 생성 시각으로 거른 목록과 당시 실측 스냅샷은 같지 않다.
- Network generation_snapshot은 별도 환경별 network_configuration_snapshots에 저장한다(:684). 기존 기간 스냅샷을 읽었다고 해서 그것을 새 실시간 관측본으로 다시 저장하지 않는다.
- HTML 및 공개 JSON 파일을 먼저 만들고 DB save_report(:44) 트랜잭션에서 run/detail/snapshot/artifact/errors/facts를 저장한다. DB required 여부에 따라 저장 실패는 예외 또는 로그 경로로 나뉜다. 수집 직후 독립 불변 스냅샷을 확정하는 T07 구조는 아직 없다.
- ReportResult.from_dict(:396)는 있으나 운영 재렌더 경로에서 사용하는 호출부는 발견하지 못했다. 현재 보고서 보기는 기존 HTML 파일을 반환한다.

### 5.3 부분 수집·경고와 분석

report 상태, 작업 상태, 데이터셋 상태는 서로 다른 축이다.

- report: collection_errors가 있으면 PARTIAL_SUCCESS, 없으면 SUCCESS인 저장 경로다. 경고만 있어도 report는 SUCCESS일 수 있다.
- job: runner가 정상 반환하면 complete가 SUCCESS로 끝낸다. 결과 보고서의 PARTIAL_SUCCESS가 작업 상태에 그대로 복사되는 구조가 아니다.
- dataset 판정(app/runner.py:1322): 요청 안 함 → NOT_REQUESTED, 오류+레코드 → PARTIAL, 오류+자료 없음 → FAILED, 경고 존재 → PARTIAL, 정상 자료 → COLLECTED, 정상 빈 결과 → COLLECTED_EMPTY.
- 분석의 AVAILABLE/NOT_REQUESTED 등 품질 판정과 OBSERVED/CALCULATED 등 출처 표현도 별개다. “부분 수집”은 항상 HTTP 오류나 권한 거부를 뜻하지 않는다.

analysis_enabled는 app/report_options.py:282에서 운영 요약 섹션 선택 및 operational_analysis.enabled에 따라 결정되며 runner의 전역 REPORT_OPERATIONAL_ANALYSIS_ENABLED도 적용된다. WMS/Security 추가 수집 토글은 기본 false다.

app/report_analysis/engine.py:23의 **ANALYSIS_VERSION=1.3**은 이미 있다. analyze_report(:39)는 ReportResult, 이전 비교 자료, 정책을 입력받아 데이터 품질, 지표, 이벤트, 변경, 가용성, 보안, 비용, findings 및 overall을 계산한다. governance는 현행 미요청 상태도 다룬다. 엔진 자체의 결정성과 입력을 다시 조회하는 runner의 재현성은 분리해서 보아야 한다.

app/report_options.py:8–69는 CPU·메모리·디스크 warning 기본 90%, critical 95%, 지속 15분 등을 정한다. 이 여섯 백분율 필드의 하한이 90%, 상한이 100%다. 비용 변화 20%, 가용성 warning 99/critical 95, 응답 3000ms 등 다른 항목은 별도 기준이다. 하한 완화는 단순 UI 수정이 아니라 판정 정책 변경이다.

**T00B-5의 전제 수정:** 분석은 AVG가 없으면 MIN/MAX로 대체한다(app/report_analysis/metrics.py:192). metrics.py:277, html_renderer.py:3956, database/report_repository.py:968–1042가 raw.dps의 시각·값을 읽는다. values만 남기고 raw를 지우면 시간 정보와 소비자 동작이 깨질 수 있다. 정규 시계열 표현·기존 스냅샷 호환·소비자 전환을 먼저 설계해야 한다.

## 6. 재현성 저해 요소 목록 (파일:줄, 이유)

확인된 경로와 재현 시 위험을 구분한다. 아래는 모든 항목이 지금 사용자에게 오작동을 일으킨다는 뜻이 아니라 T07의 동일 입력 재현을 위해 고정·검증해야 할 지점이다.

| 위치 | 확인 사실 | 재현성 영향·후속 조건 |
|---|---|---|
| app/report_models.py:65, app/runner.py:2495 | generated_at 기본값/생성 시 현재 시각 사용 | 재실행 시 새 시각을 만들지 말고 저장된 입력에서 주입 |
| app/renderers/html_renderer.py:2741 | generated_at이 보고서 HTML에 포함됨 | 수집 내용이 같아도 생성 시각이 바뀌면 바이트가 달라짐 |
| app/runner.py:307 | 청구 기간·현재 월 관련 컨텍스트 계산 | 계산 시점과 기준을 저장해야 과거 비용 재분석 가능 |
| app/runner.py:1277, database/report_repository.py:369 | 이전 보고서/비교 기준을 DB에서 다시 선택 | 이후 생성·삭제된 이전 보고서에 따라 비교 결과가 달라짐. baseline ID/내용 고정 필요 |
| app/runner.py:1496 | 수집→분석→렌더→저장이 결합 | 재현 명령으로 이 경로 전체를 재실행하면 외부 API를 다시 호출하게 됨 |
| app/report_models.py:377,396 | 내부 스냅샷 직렬화와 from_dict는 존재하지만 네트워크 generation_snapshot 재구성이 빠짐 | 별도 network_configuration_snapshots까지 합쳐야 전체 보고서 입력 복원 |
| app/renderers/html_renderer.py:3869,4074 | 시계열/버킷 입력 순서에 따라 색·ID 배정 | 동등한 자료라도 입력 순서가 다르면 HTML/시각 배치 차이 가능 |
| app/renderers/html_renderer.py:4849,4860 | product_data.items 순회·비정렬 JSON 출력 | JSONB 왕복 뒤 객체 순서 변화에 대한 안정 정렬 검증 필요 |
| app/renderers/html_renderer.py:5327,5332 | 식별자 없는 이벤트 행 dedup에 id(row) fallback | 메모리 객체 공유 여부와 역직렬화 결과 차이에 의존할 수 있음 |
| database/report_repository.py:635,1634 | 현재 JSON 직렬화 문자열을 해시, canonical sort 규약 없음 | DB JSONB에서 읽어 재직렬화한 해시와 최초 해시를 단순 비교할 수 없음 |
| database/report_repository.py:548,640 | collector/normalizer/renderer 버전에 1.5 상수 사용 | 실제 코드 버전·스키마 버전·분석 버전을 구분한 매니페스트 필요 |
| webapp/repository.py:3982 | 익명화가 snapshot JSONB를 갱신하는 경로 존재 | 기존 snapshot 해시 갱신/검증 의미와 익명화 이후 재현 정책을 함께 결정 |
| database/report_repository.py:609 | 동일 run 저장 시 상세 데이터를 교체하는 경로 | 재저장을 불변 원본 확정으로 간주하면 안 됨 |
| app/report_options.py:327, app/report_models.py:396 | 구형 설정을 현재 기본값으로 정규화 | 구형 schema별 기본값·해석 고정 없이는 같은 설정 JSON의 의미가 변할 수 있음 |
| app/renderers/html_renderer.py:678–689,2698,2722 | 상수 스크립트·인라인 스타일, 현재 스크립트 CSP 해시 상수 있음 | 버전별 렌더 코드/자산을 보존하지 않으면 구형 출력 바이트 재생 불가 |

구분해야 할 비위험/기존 보장:

- 렌더 함수에서 직접 now()/난수 호출을 발견한 것은 아니다. 현재 시각은 주로 runner/model에서 입력된다.
- webapp/presentation.py의 현재 시각은 포털 UI용이며 보관된 보고서 본문의 재현성 문제와 다르다. 인증용 난수를 제거할 대상도 아니다.
- app/report_analysis 엔진은 이미 결정적 분석을 지향한다. ANALYSIS_VERSION을 새로 중복 도입할 필요는 없다.
- 운영 경로의 JSONB 왕복·네트워크 스냅샷 결합·구형 렌더 버전을 포함한 비트 동일 재현은 이번 테스트 통과만으로 검증된 것이 아니다.
- 과거 HTML은 수정하지 않는다. 기존 content 라우트의 원본 제공과 신규 재현 산출물 생성은 분리해야 한다.

## 7. 저장소 레이아웃과 보존·정리 동작

### 7.1 파일과 DB의 경계

- Helm artifacts PVC mount는 /app/output, REPORT_OUTPUT_DIR 설정은 /app/output/report다. PostgreSQL 데이터는 별도 /var/lib/postgresql/data 볼륨이다.
- 저장소 Helm 기본 artifacts 용량은 20Gi다. 00-context의 9.75GiB는 운영 관측 기록이며 **현재 실제 PVC 용량은 미확인**이다.
- worker는 `<output>/<customer_code>/<account_code 또는 UUID>/<job_uuid>`를 runner에 전달한다(webapp/job_worker.py:80).
- runner 생성자는 기본 고객이 아니면 customer_id를 다시 붙인다(app/runner.py:84). 따라서 해당 경로에서는 `<output>/<customer>/<account>/<job>/<customer>/ncp_report_<period.file_suffix>.html|json` 형태가 될 수 있다. 중복 고객 디렉터리를 임의로 정리/이동하면 기존 URI가 깨진다.
- CLI 기본 경로는 runner의 ./output/report와 설정 모듈의 ./reports 등 진입점에 차이가 있어 실제 전달값을 기준으로 판단해야 한다.
- 일반 산출물은 HTML·공개 JSON이다. 내부 재현 스냅샷과 시계열·네트워크 규칙은 DB에 있다. “HTML 옆 JSON 파일 = 내부 원본 전체”가 아니다.
- 로고는 tenant_branding DB 바이트에서 data URI로 출력한다. 업로드는 PNG/JPEG/WebP, 최대 512KiB, 크기·픽셀 제한을 검사한다.

### 7.2 정리 실행과 보호 조건

1. webapp/repository.py:2374가 관리자 목록 후보를 계산한다(상한 500개). 보호 사유는 ACTIVE, CLEANUP_QUEUED, POLICY_FOREVER, LATEST, RETENTION이다.
2. POST /msp/data-cleanup은 선택·확인 문구·권한을 검사하고 report_runs.cleanup_*에 요청을 남긴다(:2470). 요청 시 즉시 파일 전체를 지우는 방식이 아니다.
3. webapp/artifact_cleanup.py가 만료 정책 enqueue(:2664), 요청 처리(:2782), 파일 outbox 재시도(:3032)를 수행한다.
4. delete_report(:3128)는 실제 실행 시 보호 조건을 재검사한다. 자동 보존 정리는 명시적 DAYS 정책과 만료를 확인한다. **설정이 없다는 이유만으로 자동 삭제를 허용하지 않는다.**
5. 삭제할 artifact/raw_payload_ref/metric_series 파일 URI와 기대 해시·크기를 outbox에 남기고 DB run을 삭제한다. FK CASCADE로 snapshot, network snapshot, 지표, 이벤트, 비용, 오류, artifact 등이 함께 삭제된다. job/일부 최신 fact 참조는 NULL 처리된다.
6. DB 커밋 후 파일을 삭제하며 허용 경로·해시·크기·다른 참조를 검사한다. 실패는 outbox에서 재시도한다. DB 삭제 이후 파일만 남는 상태도 있을 수 있다.

단건 삭제와 대량 정리는 동일 권한·보호 정책이 아니다. 단건 보고서 삭제는 MSP 운영자도 가능하고 protect_latest 기본 false, 대량 정리는 관리자만 가능하고 최신 정상본 보호를 켠다. 실행 중·영구 보존·보존 기한 등 다른 보호 조건은 남는다(11절 질문).

현재 모델에는 독립 legal hold, 산출물과 재현 원본의 별도 수명 정책, 완전한 재현 원본 영구 보존 계약이 없다. T07/T08은 CASCADE 및 기존 정리 outbox를 함께 고려해야 한다. 삭제 후 해당 스냅샷에서 재현할 수 있다고 안내하면 안 된다.

### 7.3 구형 HTML의 /static/ 참조 조사

로컬 output 아래 HTML **74개**에 대해 `rg -l '/static/' output -g '*.html'` 결과는 **0개**였다. 본문 내용을 대량 출력하지 않고 참조 여부만 검사했다.

이는 **로컬 샘플 결과**다. 운영 PVC는 접속하지 않았으므로 전체 보관 HTML의 /static/ 참조 유무는 **미확인**이다. T01에서 구형 CSS를 삭제해도 된다는 근거로 사용하지 않는다. 후속 허용된 점검에서 운영 PVC의 HTML을 읽기 전용으로 같은 패턴 검색하고, 외부 URL·상대 정적 자산 참조도 함께 확인해야 한다.

현재 신규 HTML은 HTML_REPORT_STYLES와 REPORT_DISPLAY_STYLES 둘 다 인라인으로 포함한다(html_renderer.py:2722). “표시 보정 CSS는 iframe에만 적용된다”는 가정과 현재 코드는 다르다. 기존 산출물은 생성 버전에 따라 별도로 판단한다.

## 8. Insight 알람·알림 현황

### 8.1 대시보드 출처와 반복 알람 묶기

- webapp/repository.py:1604는 접근 가능한 환경의 최근 완료 SUCCESS/PARTIAL_SUCCESS 보고서와 report_snapshots를 읽는다. 현재 패널은 별도 실시간 Insight sweep이나 insight_events 테이블 직접 집계가 아니다.
- SQL은 KST 어제 0시 이후 후보를 가져오고 webapp/insight_dashboard.py:9가 **오늘 완료된 보고서**를 최종 선별한다. 알람 발생일 자체가 오늘이라는 보장은 없고, 오늘 보고서를 생성하지 않은 고객의 현재 알람도 보장하지 않는다.
- 그룹 키는 고객·계정·환경 + 상품 + 자원 + 규칙 + 지표/조건/단위/집계/간격 + 정렬된 차원이다. 서로 다른 계정은 합치지 않는다.
- CronJob controller와 클러스터/namespace/Pod 식별이 갖춰진 경우에만 일시적인 Pod·nodeInstanceNo 차원을 그룹 키에서 제외한다. 그 외 Pod 알람은 임의로 합치지 않는다.
- 반복 횟수는 같은 이벤트가 여러 보고서에 포함된 횟수가 아니다. event ID를 우선 중복 제거하며, ID가 없으면 원래 차원·발생 시각을 포함한 occurrence identity를 사용한다. 식별 근거가 없는 행은 무리하게 하나로 합치지 않는다.
- 최신 보고서의 상태를 우선하고 최초/최근 시각, 가장 높은 심각도, 발생별 Pod/노드/보고서 근거를 남긴다. 종료 시각 없음은 **종료 미확인**이지 실시간 OPEN 확정이 아니다.
- 회귀 근거: tests/test_insight_dashboard.py:28,46,58,77,99의 CronJob 6회 통합, 다른 차원, 일반 Pod 분리, 보고서 중복, 계정 분리 테스트.

T09에서 그룹 fingerprint와 발생 occurrence의 고유키를 분리해야 한다. `UNIQUE(fingerprint, occurred_at)`만 쓰면 같은 순간 여러 Pod에서 발생한 별개 이벤트를 잃을 수 있다. 또한 기존 환경별 insight_events.report_run_id는 NOT NULL이므로 보고서 없이 도는 sweep이 그대로 INSERT할 수 없다.

### 8.2 API 능력: 코드 확인과 공식 미확인 분리

| 항목 | 현재 코드에서 확인 | 공식 계약 판정·추후 확인 방법 |
|---|---|---|
| 이벤트 조회 | ncp_api/cloudinsightAPI.py:109 search API, collector의 페이지 처리·응답 검사 | **미확인**. public/gov 각각 Event Search 요청·응답 계약 대조 |
| 미종료 조건 | 클라이언트에 only_fetch_un_close_event 인자가 이미 있고 JSON onlyFetchUnCloseEvent로 전달(:153). 현재 이벤트 collector는 이 인자를 지정하지 않음 | **미확인**. 시간 범위와 이 옵션의 조합, 전체 OPEN 집합 보장, 페이징 완전성 확인 |
| 종료 시각·상태 | normalizer는 endTime → end_time으로 보존, DB는 ended_at 저장. notificationStatus도 보존 | **미확인**. endTime 부재/0/null 의미와 상태 필드의 종료 의미 확인. notificationStatus를 OPEN/CLOSED로 단정하지 않음 |
| 이벤트 단건 | searchById 클라이언트 경로 존재(:163,210) | **미확인**. 조회 가능 기간·종료 이벤트 보존·권한 확인 |
| 지표 단위 | 이벤트 unit 및 지표/상품 스키마 조회 코드 존재(:624,718,747) | **미확인**. real_mem 등 실제 상품 지표의 unit·집계 의미를 메타데이터와 대조. bytes를 임의로 %로 바꾸지 않음 |
| 호출 한도 | 클라이언트 재시도·페이지 상한 구현 있음 | **미확인**. 환경·계정·API별 quota 및 429/Retry-After 규약 확인 |
| 전용 Backup | Resource Manager 자원과 서버 이미지/디스크 snapshot 경로는 존재 | **미확인**. 전용 Backup API 목록과 서버별 경로/용량/보관 기간 필드 제공 여부를 별도 대조 |

확인할 공식 문서 주소(이번에는 접속하지 않은 **문서 포털 진입 주소**):

- [NCP API 공식 문서](https://api.ncloud-docs.com/): Cloud Insight → Event Search/Search by ID, Product Schema/Metric List 항목을 찾아 위 클라이언트 경로·필드와 대조한다. public/gov 구분, 페이지 종료 조건, 필수 권한, 종료 시각, 단위, 미종료 옵션 의미를 표로 기록한다. 정확한 개별 페이지 URL은 미확인이다.
- [NCP 사용 가이드](https://guide.ncloud-docs.com/): Cloud Insight API 이용 제한·환경 지원 범위, Backup 기능/API 안내를 확인한다. 예제 응답은 자격증명·실제 고객 식별자를 제거한 고정 테스트 자료로만 사용한다.
- 같은 API 문서 포털의 비용 조회(demand/product/contract cost, 할인·VAT) 문서에서 청구 확정 시점·조회 범위 의미도 확인한다. T06의 “청구 데이터 준비 완료” 정책을 코드 추정만으로 확정하지 않는다.

이번에는 NCP 요청, 문서 검색, 한도 실험을 하지 않았다. 공식 대조 전에는 “목록에서 안 보이면 해결됨”이라는 자동 상태 전이를 활성화하지 않는 것이 안전하다.

### 8.3 포털 알림

portal_routes.py:234의 /notifications는 after 이후 작업 이벤트를 반환한다. webapp/repository.py:3349는 report_jobs의 created_at→QUEUED, started_at→RUNNING, completed_at→SUCCESS/FAILED/CANCELLED를 펼쳐 고객 범위 내 최대 100개를 조회한다. 잘못된 after는 기본 조회 시각으로 처리하고 오래된 조회 범위는 24시간으로 제한한다.

별도 알림 원장·읽음 상태·지속 보관 테이블은 없다. 폼 결과는 세션 flash이고, JS는 sessionStorage에 마지막 시각·최근 이벤트 식별자를 보관한다. portal.js:225–253은 기본 4초 폴링, 숨긴 탭 건너뛰기, 다시 표시될 때 조회를 이미 구현한다. 오류 토스트는 :153–156에서 자동 제거하지 않는다. 일반/경고 토스트는 기본 6초다.

따라서 “모든 오류 토스트가 자동으로 사라진다”, “숨긴 탭에서도 항상 호출한다”는 전제는 현재 코드와 다르다. 인증 만료에 대한 명시적 401 JSON 처리/폴링 중지는 후속 개선 대상이다. 부분 수집 report가 job SUCCESS 알림으로 표시되는 상태 축 차이도 유지·수정 의도를 정해야 한다.

## 9. 프런트엔드 자산 지도

루트 static/templates가 아니라 **webapp/static, webapp/templates**가 실제 경로다. base.html:9–14에서 아래 CSS 5개를 순서대로 로드하고 portal.js를 연결한다. 현재 버전 쿼리는 모든 파일에 일관되게 적용된 상태가 아니다.

| 자산 | 주요 역할·사용 화면 | 주의점 |
|---|---|---|
| portal.css | 셸·사이드바·카드·표·폼·로그인·기본 상태, 전 템플릿 | 1줄 압축 형태, 직접 색상/기존 CSS 변수 혼재 |
| automation.css | 계정 즉시 생성/일정 카드, 보고서 뷰어·자동화 화면 | :71의 fixed 뷰어와 720px 해제 기준; 1000px 셸 전환과 중간 폭 충돌 가능 |
| notifications.css | 토스트 영역·알림 버튼·애니메이션 | 동적 JS 클래스와 함께 검사해야 함 |
| report_settings.css | 고객 보고서 섹션 순서·선택·임계치·보존·위험 동작·details | customer_detail, schedules 등의 설정 영역 |
| ux.css | 스킵 링크·focus-visible·현재 메뉴·모바일 메뉴·표 스크롤 안내·Insight 발생 상세 | :17–18 및 reduced-motion의 !important는 접근성/기존 우선순위 이유를 검토한 뒤 대체 |
| portal.js | 메뉴, 표 overflow, 보고서 iframe/확대/인쇄, 보존/정리 선택, 토스트·폴링 | :44–86은 같은 출처 iframe 문서 접근; sandbox 전환과 함께 바꿔야 함 |
| html_report_styles.py 및 html_renderer.py | 보고서 자체 인라인 CSS·상호작용 스크립트 | 포털 CSS 병합과 보고서 산출물 변경을 분리 |

customer_detail.html, schedules.html에도 설정 정렬·일괄 선택용 인라인 JS가 남아 있다. 정적 파일만 검사하여 전체 JS를 파악했다고 하면 안 된다.

기존 포맷 헬퍼는 webapp/presentation.py의 format_kst(:15), format_duration(:35), format_status(:58, Jinja 이름 status_label), inclusive_end(:66)다. 공유 status_badge와 공통 컴포넌트 매크로 파일은 없지만 base.html 내부 menu_link 매크로는 이미 있다. “매크로가 전혀 없다”로 해석하지 않는다.

사용하지 않는 셀렉터 후보는 portal.css의 .flash/.flash.error/.flash.success다. 템플릿/JS에서 현재 참조를 발견하지 못했으나, 후보일 뿐 운영 구형 산출물까지 확인한 삭제 승인 목록은 아니다. status·tab·toast 등 동적 클래스는 정적 검색만으로 삭제하지 않는다.

현재 포털 color-scheme은 light 중심이며 디자인 시스템의 완전한 다크 모드/토큰/@layer 단일 CSS 구조는 아직 없다. 소요 시간은 Python 정수화와 webapp/repository.py:2280의 SQL bigint 변환 때문에 정밀도가 손실된다. 기존 시작/종료 datetime을 활용할 수 있는지 먼저 검토하고 밀리초 전용 DB 컬럼을 바로 추가하지 않는다.

## 10. 지시서 가정과 다른 점 (T00A·T00B·T01–T10 판정)

이 절은 후속 지시서를 자동 수정하거나 실행하는 승인이 아니다. **각 작업 시작 전에 수정 계획·영향·마이그레이션·라우트 변경을 다시 제시한다.**

| 지시서 | 판정 | 그대로 적용하면 안 되는 전제 및 보완 |
|---|---|---|
| T00A | **수정 필요** | 현재 추적 파일은 깨끗하지만 CRLF/mixed 41개를 그대로 보존 중이다. 정규화는 별도 승인·명시적 파일 단위로 하고 기존 사용자 변경과 분리한다. F841 해소를 이유로 runner:2321 의미를 확인하지 않고 삭제하지 않는다. 버전 범위·네트워크 없는 상태에서 새로운 lock/digest/CVE 결과를 확정하지 않는다. Python 선언만으로 pip -r 실행 환경이 강제되는지 검증하고 CI 실제 버전 검사와 맞춘다. |
| T00B | **수정 필요** | B-5의 “raw 삭제, values 유지, MIN/MAX 미사용” 전제가 틀린다. 세 소비자가 raw.dps를 읽고 분석에는 MIN/MAX fallback이 있다. 시각·정밀도·구형 스냅샷 호환을 보존한 후 축소해야 한다. B-1의 cryptography 목표 버전/취약점은 미확인. B-2는 기존 CSP 해시 상수 재사용 및 구형 스크립트 호환 필요. B-4 ProxyFix는 실제 신뢰 프록시 수 확인 후 적용. B-6 풀은 역할·트랜잭션 컨텍스트 격리 검증/의존성 승인 필요. B-7은 과거 표시 입력과 새 현재 백업을 구별. B-8 슬롯은 전역 상한이 아니며 기존 큐 재시도를 재사용. B-9는 기존 포맷 헬퍼에서 시작. |
| T01 | **수정 필요** | 실제 경로는 webapp/static·templates. 기존 status/시간 헬퍼를 합치고 중복 카탈로그를 만들지 않는다. 운영 보관 HTML 자산 참조는 미확인이므로 구 CSS 삭제를 유보한다. 소요 시간 정밀도는 기존 datetime부터 활용한다. 테마 사전 적용 스크립트는 T00B CSP와 조율. AGENTS의 1280px도 필수 검증 폭에 포함한다. |
| T02 | **수정 필요** | 인증된 GET /login 리다이렉트, 오류 토스트 유지, 숨긴 탭 폴링 억제가 이미 있다. 이 기능을 재구현하지 말고 누락 동작만 보완한다. 알림함 읽음/보관은 현행 모델에 없으므로 RLS·POST/CSRF 포함 설계 필요. SYSTEM_ADMIN을 MSP_ADMIN과 자동 동등 취급하지 않는다. 아직 없는 후속 화면으로 끊긴 링크를 만들지 않는다. |
| T03 | **수정 필요** | ORM 가정 없이 원시 SQL과 기존 범위 검사에 적용한다. /history의 tenant_id·q·status·page를 유지하고, 현재 잘못된 page/status는 400이라는 동작 변경을 명시한다. /msp/users?tenant_id=는 현재 폼 사전 선택이지 목록 필터가 아니다. 사용자 복수 고객 소속을 보존한다. 공통 50/최대 200 페이지 정책은 현재 각 목록 상한과 다르다. |
| T04 | **수정 필요** | 설정·보존은 tenant_report_settings 한 JSON 행이다. 기존 감사 기록을 활용하되 before/after가 필요하면 확장한다. 출력용 자원 필터와 수집/모니터링 합집합을 구분한다(11절). 90% 하한 변경은 사용자 결정 후 적용한다. 현재 section_order 폼 이름/보존 정책을 보존한다. T07 이전에는 완전한 재렌더 미리보기가 없고 JS 없는 정렬은 서버 제출 대안이 필요하다. |
| T05 | **수정 필요** | 완료 조건의 “업/다운 마이그레이션”은 forward-only 지침과 충돌한다. 추가형 변경·재실행 2회·기존 데이터 검증·전진 수정 계획으로 교체한다. 새 control 프로필 테이블은 tenant/account/env 관계와 RLS를 따라야 한다. RANGE↔CUSTOM 매핑과 RANGE의 DAILY/ANY fallback 우선순위를 명시한다. 기존 고객 설정을 이동해도 선택·분석·보존·브랜딩이 같아야 한다. |
| T06 | **수정 필요** | 활성 일정은 account_report_schedules이며 timezone·weekly_day·monthly_day와 큐 재시도가 이미 있다. 구형 report_schedules로 새 실행기를 만들지 않는다. 작업 상태는 PENDING이 아니라 QUEUED, WAITING_DATA는 신규 제약·UI 변경이다. 메일 발송 CLI와 예약 worker 전달은 별개. 공유 링크는 새로운 권한 경계이므로 별도 승인 필요. 한도·청구 확정 시점은 공식 미확인. 결정적 분산의 수용량 초과 처리와 전역 동시성은 T00B와 함께 정의한다. |
| T07 | **수정 필요** | 기존 report_snapshots·from_dict·ANALYSIS_VERSION을 활용한다. options는 이미 JSON에 있으나 큐 시점의 불변 프로필/기준 전체를 고정한 것은 아니다. 별도 network snapshot 결합, baseline·집계 시각·canonical hash·구형 버전 호환을 포함한다. CASCADE 정리와 원본 보존 정책을 함께 변경하고 현재 파일 경로/보관 HTML은 보존한다. 스키마 버전 1.5와 코드/분석 버전을 혼동하지 않는다. |
| T08 | **수정 필요** | 본문은 Jinja 템플릿이 아니라 대형 Python 렌더러다. 신규 기능을 800줄 초과 기존 파일에 계속 추가하지 않는다. 신규 HTML에 두 스타일 묶음이 이미 인라인 포함된 점을 반영하고 기존 산출물은 수정하지 않는다. T00B의 iframe sandbox/postMessage 후속 계획과 현행 contentDocument·contentWindow.print 의존을 함께 해소해야 한다. real_mem 단위는 추정하지 않는다. |
| T09 | **수정 필요** | 미종료 옵션 클라이언트는 이미 있으나 공식 전체 OPEN 목록 계약은 미확인이다. 확인 전 NOT_SEEN→해결 자동 판정을 넣지 않는다. 기존 insight_events는 report_run_id NOT NULL이므로 독립 sweep 저장 방법을 명시한다. 그룹 fingerprint와 발생 고유키를 분리해 같은 시각 다른 Pod 이벤트를 보존한다. 현재 CronJob 묶기·보고서 중복 제거 회귀 테스트를 재사용한다. |
| T10 | **그대로 진행 가능(선행 구현 완료 전제)** | 4개 폭·양 테마·접근성·보이는 텍스트 검사·결정성·보안·운영 문서의 검증 목표는 실제 스택에 맞는다. 구체 실행은 앞 작업 완료 후, 필요한 개발 의존성은 승인 후 추가한다. snapshot fixture는 비밀/고객 정보를 제거하고 T07 버전·해시 규약에 맞춘다. 공유 링크 테스트는 실제 승인·구현 범위에 맞춰 실행한다. 현재 T00에서 이 검증을 완료했다고 주장하지 않는다. |

기존 자료 대비 특히 중요한 정정: 로그인 GET 리다이렉트는 구현됨, 오류 토스트는 지속 표시됨, 탭 숨김 폴링 억제는 구현됨, 작업 재시도는 이미 있음, 원시 시계열은 아직 실제 소비됨, 신규 HTML에 표시 보정 스타일도 포함됨. 이전 리뷰의 운영 측정 수치와 지금의 소스 확인 결과를 섞지 않는다.

## 11. 확인이 필요한 질문 (사용자에게)

1. **app/runner.py:2321에서 범주로 걸러낸 infrastructure_data가 쓰이지 않는 것이 의도인가요?** 이후 모니터링 수집과 ReportResult 생성은 원본 infrastructure를 사용합니다(:2341,2473). 다만 ReportResult.display_infrastructure(app/report_models.py:100)와 렌더러(:826)는 출력 범주를 다시 적용하고, 내부 원본 보관에는 모니터링 전용 자원이 필요할 수 있습니다. “목록에서만 숨기고 수집·분석·저장에는 유지”가 의도인지, 이 단계부터 제외하려는 것인지 결정해야 합니다. 이번에는 변수 삭제/대입 교체를 하지 않았습니다.
2. **MSP 운영자에게 보고서 단건 삭제를 허용하는 것이 의도인가요?** portal_routes.py:172는 MSP_ADMIN뿐 아니라 MSP_OPERATOR/SYSTEM_ADMIN에도 범위 내 삭제를 허용합니다. 관리자 전용 대량 정리와 다르고, 단건 삭제는 최신 정상본 보호 옵션도 기본 꺼져 있습니다. 현행 권한·보호 차이를 유지할지, 관리자 전용 및 최신본 보호로 통일할지 확인이 필요합니다. 권한은 변경하지 않았습니다.
3. **CPU·메모리·디스크 경고 임계치의 최소 90% 제한을 유지할까요?** app/report_options.py는 warning/critical 여섯 필드 모두 90–100 범위로 제한합니다. 70/80% 조기 경고 등을 허용하려면 UI 범위뿐 아니라 서버 검증·기본값·warning<critical 정책·분석 회귀를 함께 정해야 합니다. 이번에는 현행 제한을 유지했습니다.

추가 미확인 사항은 질문에 임의 답을 붙이지 않았다. 운영 PVC 자산 참조, 실제 프록시 구조, NCP 공식 종료/단위/호출 한도는 7·8절의 확인 방법으로 별도 검증해야 한다.

## 12. 열거형·파라미터·명령 매핑

### 12.1 보고서·작업·상태

| 구분 | 현행 값/규칙 | 지시서와의 매핑·주의 |
|---|---|---|
| 즉시 생성 폼 | _account_automation.html: DAILY, WEEKLY, MONTHLY, 시간 범위 hidden CUSTOM | 설계 RANGE는 현행 CUSTOM에 해당 |
| 일정 유형 | DAILY/WEEKLY/MONTHLY | ANY/RANGE 일정은 현재 없음 |
| 작업·보고서 유형 | DAILY/WEEKLY/MONTHLY/CUSTOM | DB·CLI·폼 모두 한 매핑 경계에서 호환 유지; 단순 문자열 전면 치환 금지 |
| DAILY target_value | YYYY-MM-DD | 예약은 직전 일 기준 |
| WEEKLY target_value | YYYY-Www | ISO 주, 월요일 시작 |
| MONTHLY target_value | YYYY-MM | 예약은 직전 월 기준 |
| CUSTOM 입력 | start_datetime/end_datetime, KST 해석, 종료 미포함, 같은 월 안 | CLI date 범위와 datetime 경계 해석을 구별 |
| 프로필 ANY | 현재 없음 | T05 신규 프로필 선택 규칙, 기존 보고서 유형 아님 |
| job.status | QUEUED/RUNNING/SUCCESS/FAILED/CANCELLED | 설계 PENDING↔QUEUED. PARTIAL_SUCCESS는 job 저장 상태가 아님 |
| report_run.status | QUEUED/RUNNING/PARTIAL_SUCCESS/SUCCESS/FAILED/RETRYING/CANCELLED | 이력 UI의 job/report 통합 표시와 원본 상태를 구별 |
| trigger_type(작업) | MANUAL/SCHEDULED/RETRY | 재시도·재현 job_type과 다름 |
| job_type | 독립 컬럼 없음 | COLLECT_AND_RENDER/RERENDER/RECOLLECT/VERIFY는 후속 도입 대상 |
| dataset 상태 | NOT_REQUESTED/PARTIAL/FAILED/COLLECTED/COLLECTED_EMPTY | 분석 품질·출처와 별개 |
| 출처 상태 | OBSERVED/CALCULATED 등 | 수집 성공·오류와 동일 축 아님 |
| tenant.status | ACTIVE/SUSPENDED/ONBOARDING/OFFBOARDED | 화면 상태 라벨은 공통 헬퍼로 연결할 대상 |
| cloud_account.status | ACTIVE/DISABLED/CREDENTIAL_ERROR | 사용자 status와 혼합 금지 |
| user.status | INVITED/ACTIVE/LOCKED/DISABLED | platform role 및 membership과 별개 |
| membership.role | CUSTOMER_ADMIN/CUSTOMER_VIEWER | 복수 고객 소속 가능 |
| platform.role | MSP_OPERATOR/MSP_ADMIN/SYSTEM_ADMIN/SECURITY_AUDITOR | 이름만으로 관리자 권한을 확대하지 않음 |
| event_cases.status | NEW/ACKNOWLEDGED/IN_PROGRESS/RESOLVED/IGNORED/NOT_DETECTED | T09 OPEN/해결 상태 머신과 직접 치환 금지 |
| 보존 정책 | DAYS(1–3650)/FOREVER, 유형 DAILY/WEEKLY/MONTHLY | 기본 표시와 자동 삭제의 명시적 설정 여부를 구별 |

새 상태·유형은 코드 매핑뿐 아니라 SQL CHECK, 인덱스 조건, 템플릿, 필터, 알림, 기존 데이터 호환을 함께 검토한다.

### 12.2 실제 쿼리/폼 파라미터

| 화면·동작 | 파라미터와 현행 처리 |
|---|---|
| /history | tenant_id, q(최대 200자), status, page(1–100000). 페이지당 50, 다음 페이지 판단용 51행 조회. 잘못된 status/page는 400, 접근 불가 tenant는 404 |
| /msp/users?tenant_id= | selected_tenant_id로 넘겨 고객 연결 폼 사전 선택. 사용자 목록 자체를 필터하지 않음 |
| /notifications | after(ISO 시각), 오래된 조회는 최대 24시간 범위, 잘못된 값은 기본 시각 |
| /msp/customers/<environment> | 환경은 쿼리가 아니라 경로. 현재 일반 목록 필터/페이지 파라미터 없음 |
| /msp/schedules, /portal, /msp/data-cleanup | 공통 검색·페이지 인터페이스 아직 없음. 각 조회의 별도 상한 적용(포털 보고서/작업 각 100, 정리 500 등) |
| 즉시 생성 POST | report_type, target_value 또는 start_datetime/end_datetime, csrf_token |
| 일정 POST | report_type, run_hour, run_minute, weekly_day/monthly_day, enabled 등. 주요일 1–7, 월일 1–28 |
| 출력 설정 POST | sections, section_order, resource_categories, monitoring_categories와 운영 분석·임계치 관련 필드. 현행 section_order 이름을 임의로 section_order[]로 바꾸지 않음 |

### 12.3 정리 화면의 전체 상태 코드

이 화면의 “정리 상태”는 단일 status enum 컬럼이 아니라 eligible/protection_reason/cleanup_*로 합성된다(data_cleanup.html:9–20, webapp/repository.py:2374).

| 코드/조건 | 표시·의미 |
|---|---|
| eligible=true, protection_reason 없음 | 정리 가능 |
| ACTIVE | 보호됨 / 실행 중 |
| LATEST | 보호됨 / 계정·보고서 유형별 최신 정상본 |
| RETENTION | 보호됨 / 보존 기한 내 |
| POLICY_FOREVER | 보호됨 / 영구 보존 정책 |
| CLEANUP_QUEUED | 정리 요청됨; 시도 횟수·다음 시도 시각 |
| INVALID_CLEANUP_REQUEST | 요청 검증 실패 |
| PROTECTED_AT_EXECUTION | 실행 시점 보호 조건 확인 |
| DELETE_FAILED | 정리 처리 실패 |

뒤 세 값은 cleanup_last_error_code 표시용이며 앞 다섯 보호 사유와 같은 enum이 아니다. 삭제 완료한 보고서는 후보 행 자체가 없어지므로 별도 DELETED 행으로 보존되는 화면이 아니다.

### 12.4 CLI 진입점과 확장 위치

다음은 **확인한 실행 인터페이스**이며 이번에 실제 생성·관리·정리 명령을 실행하지 않았다.

| 용도 | 현행 명령/위치 |
|---|---|
| 관리자 CLI | `python -m webapp.cli`, argparse subparsers는 webapp/cli.py:33 |
| MSP 초기 관리자 | `python -m webapp.cli bootstrap-admin --email <주소> --display-name <이름>` |
| 고객 사용자 | `python -m webapp.cli create-customer-user --email <주소> --display-name <이름> --tenant-code <코드> --role CUSTOMER_VIEWER` |
| 보고서 직접 생성 | `python main.py` + --target-day / --target-week / --target-month / --start-date·--end-date / --start-datetime·--end-datetime |
| 직접 생성 추가 옵션 | --output-dir, --customer-id, --customer-name, --api-type public/gov, --region, --send-email, --email-to |
| 저장 계정 단발 생성 | `python -m webapp.worker --account-id <UUID> --target-day <날짜>` 또는 --target-month |
| 예약 생성 | `python -m webapp.scheduler` |
| 큐 실행 | `python -m webapp.job_worker --environment public`(또는 gov), --once 지원 |
| 산출물 정리 | `python -m webapp.artifact_cleanup --limit <건수> --interval-seconds <초>` |
| 테스트 | `python -m pytest -q` |

지시서의 <cli>는 **python -m webapp.cli**로 치환하는 것이 기존 관리 방식에 맞다. 현재 maintenance, snapshot verify, rerender 하위 명령은 없다. 필요한 작업 시 이 argparse에 최소 subcommand를 연결하고 실제 처리 코드는 해당 책임 모듈에 둔다. 비밀번호는 getpass 또는 지정된 bootstrap 환경변수로 받으며 명령줄 평문 인자로 추가하지 않는다.

### 12.5 환경변수 이름 목록(값 제외)

조사한 코드·공개 배포 정의에 사용되는 이름이다. 비밀 파일 내용이나 실제 주입 값을 확인했다는 뜻이 아니다. 동적 credential reference가 지정하는 임의 이름까지 열거한 목록은 아니다.

- 앱·인증: APP_VERSION, APP_SOURCE_REVISION, WEB_SECRET_KEY, WEB_COOKIE_SECURE, CREDENTIAL_MASTER_KEY_FILE.
- 로깅·HTTP: LOG_LEVEL, LOG_FILE, API_TIMEOUT, API_RETRY_COUNT.
- NCP·고객: NCP_ACCESS_KEY, NCP_SECRET_KEY, NCP_API_TYPE, NCP_REGION, NCP_CUSTOMER_ID, NCP_CUSTOMER_NAME, NCP_CREDENTIAL_REF.
- 보고서: REPORT_OUTPUT_DIR, REPORT_OPERATIONAL_ANALYSIS_ENABLED, REPORT_EMAIL_TO.
- DB: REPORT_DB_CONFIG_FILE, REPORT_DB_ENABLED, REPORT_DB_REQUIRED, REPORT_DB_ROLE, REPORT_DATABASE_URL, REPORT_DB_HOST, REPORT_DB_PORT, REPORT_DB_NAME, REPORT_DB_USER, REPORT_DB_PASSWORD, REPORT_DB_SSLMODE, REPORT_DB_CONNECT_TIMEOUT, REPORT_DB_APPLICATION_NAME, REPORT_DB_TENANT_ID.
- 배포 DB 연결·역할: DB_HOST, DB_PORT, DB_NAME, DB_MSP_APP_PASSWORD, DB_CONTROL_APP_PASSWORD, DB_PUBLIC_WORKER_PASSWORD, DB_GOV_WORKER_PASSWORD.
- 작업 루프: SCHEDULER_POLL_SECONDS, WORKER_STALE_MINUTES, WORKER_POLL_SECONDS.
- 메일: SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USERNAME, SMTP_PASSWORD, SMTP_USE_TLS, SMTP_USE_SSL, SMTP_TIMEOUT.
- 초기 사용자: BOOTSTRAP_MSP_PASSWORD, BOOTSTRAP_CUSTOMER_PASSWORD.
- DB 컨테이너·마이그레이션: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, REPORT_SCHEMA_VERSION, DB_WAIT_SECONDS, TZ.
- 테스트 opt-in: REPORT_DB_INTEGRATION_TEST, REPORT_DB_WORKER_INTEGRATION_TEST. **이번에 설정하지 않음.**

### 12.6 T00 완료 조건과 넘겨줄 범위

- [x] 기존 자료를 먼저 읽고 실제 코드와 대조했다. AGENTS.md 6절의 구조는 확인했고 차이는 각 절과 10절에 기록했다.
- [x] 12개 절, 전체 명시적 라우트·POST, 데이터/저장/분석/알림/CLI/상태 매핑을 기록했다.
- [x] T00A·T00B·T01–T10 각각 판정했다. 6절에 파일:줄 단위 재현성 확인 지점을 남겼다.
- [x] 공식 문서 대조는 미확인으로 두고 문서 주소와 확인 방법만 남겼다. 인터넷을 사용하지 않았다.
- [x] 요청된 세 질문을 11절에 포함했다. 정책·권한·임계치를 임의 변경하지 않았다.
- [x] 허용된 테스트 명령만 사용했고 기본 환경 실패, 기존 가상환경 성공, DB 5개 skip을 모두 기록했다.
- [x] 최종 보존 검사: 기존 추적 파일 269개 SHA-256 모두 동일, HEAD 동일, 스테이징 변경 없음. 기존 미추적 3개에 이 문서 1개만 추가됐다. 충돌 표식·줄 끝 공백 및 12개 절 구성을 검사했다.
- [x] 이 문서 외 소스·설정·지시서를 변경하지 않는다. 문서는 작업 트리에만 남기고 커밋·배포하지 않는다.

다음 작업은 이 조사 결과와 11절 정책 결정을 검토한 뒤 사용자가 지정한다. T00A/T00B 또는 UI 개편을 자동으로 이어서 실행하지 않는다.
