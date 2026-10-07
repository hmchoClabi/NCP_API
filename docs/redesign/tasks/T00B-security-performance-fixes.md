# T00B — 보안·성능 긴급 수정 + 정책 결정 반영

> 선행: T00A(최소 A-1·A-4). 근거: 코드 점검 리포트 03·05·06절, `docs/redesign/current-map.md`(T00 조사), `docs/redesign/decisions.md`(D1–D3).
> **항목마다 별도 PR**로 진행합니다. 각 PR은 테스트를 먼저 추가하고(현재 동작 고정 또는 실패 재현) 수정합니다.
> 이 지시서는 T00 조사 결과(2026-10-07)를 반영해 개정했습니다. 본문과 `current-map.md`가 다르면 계획 단계에서 차이를 보고하세요.

| PR | 내용 | 노력 | 네트워크 |
|---|---|---|---|
| B-1 | cryptography 상한 해제 | S | **필요**(버전·취약점 확인) |
| B-2 | 보안 헤더 + 한국어 오류 페이지 + UUID 경로 + XHR 401 | S | 불필요 |
| B-3 | 설정 누락 시 기동 실패(비밀키·쿠키) + SMTP 평문 로그인 차단 | S | 불필요 |
| B-4 | 로그인 시도 제한 + 계정 존재 시간차 제거 + 세션 위생 | M | 불필요 |
| B-5 | 지표 시계열 저장 표현 정리(중복 제거, **데이터 손실 없음**) + 스냅샷 조회 경량화 | M | 불필요 |
| B-6 | DB 커넥션 풀 + 정적·헬스 요청 인증 제외 + 정적 캐시 | S–M | **필요**(새 의존성 설치) |
| B-7 | 네트워크 구성 중복 수집 제거(같은 관측의 재사용만) | S | 불필요 |
| B-8 | 워커 다중 슬롯 + 전역 동시성 상한 + 하트비트 + HTTP 재시도 개선 | S–M | 불필요 |
| B-9 | 리포트 뷰어 레이아웃 겹침 + 상태 라벨 최소 정리 | S | 불필요 |
| B-10 | **정책 반영**: D2 단건 삭제 최신본 보호, D3 임계치 하한 50% | S | 불필요 |

> **네트워크가 필요한 단계**: Codex Agent 모드에는 인터넷이 없습니다. 해당 단계는 코드·문서 변경과 실행할 명령만 준비하고,
> 사용자가 직접 실행하거나(결과를 대화에 붙여 넣음) 그 단계에 한해 네트워크를 허용받은 뒤 진행합니다. 결과를 추측해 적지 않습니다.

---

## B-1 cryptography 상한 해제
- `requirements.txt`(T00A 이후에는 `requirements.in`)의 `cryptography>=44.0.0,<46`을 최신 안정 메이저로 올립니다. **목표 버전과 남는 취약점 수는 네트워크 환경에서 확인**:
  `python -m pip index versions cryptography`, `python -m pip_audit -r requirements.txt`(사용자 실행 또는 CI).
- 사용처는 AES-GCM 봉투 암호화(T00에서 확인한 `webapp/security.py` 등). **기존에 암호화된 값이 새 버전에서 복호화되는지** 고정 픽스처(테스트용 키·평문)로 왕복 테스트.
- 완료: 전체 테스트 통과, pip-audit 결과 첨부(사용자 실행 결과도 가능).

## B-2 보안 헤더·오류 페이지·UUID 경로·XHR 401
1. `webapp/app.py` 앱 팩토리에 `after_request` 훅으로 `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
   `X-Frame-Options: DENY`(리포트 본문 라우트는 현재 값 유지), `Content-Security-Policy: frame-ancestors 'self'; object-src 'none'; base-uri 'none'`,
   쿠키 Secure 환경에서 `Strict-Transport-Security: max-age=31536000`, 인증된 비정적 응답 `Cache-Control: no-store`. **이미 설정된 헤더는 덮어쓰지 않음**(`setdefault`).
2. `/reports/<id>/content`의 CSP: `html_renderer.py:678–689` 부근에 **이미 있는 렌더러 스크립트 CSP 해시 상수**를 재사용합니다.
   요청마다 파일을 읽어 모든 `<script>` 해시를 허용하는 현행 방식(`portal_routes.py:305-314`)은, 상수 해시와 일치하지 않는 **구형 산출물**을 위해
   "산출물별 해시를 렌더 시 저장 → 없으면 현행 방식" 폴백으로만 남깁니다. 어느 쪽을 택할지 계획에 적습니다.
   iframe `sandbox`는 `portal.js:44–86`이 `contentDocument`에 접근하므로 이번 PR에서 하지 않습니다(T08에서 postMessage 전환과 함께).
3. 한국어 오류 템플릿 `webapp/templates/errors/{400,403,404,500}.html`(앱 셸 없는 단순 레이아웃). 로그인 CSRF 실패는 "세션이 만료되었습니다. 다시 로그인해 주세요."
   XHR(`Accept: application/json`) 요청은 JSON 오류, 세션 만료 시 302 대신 **401 JSON** → `portal.js` 폴링은 401에서 중지(현행 숨긴 탭 건너뛰기·오류 토스트 유지는 이미 구현되어 있으니 건드리지 않음).
4. ID 경로에 `<uuid:...>` 컨버터 적용(현재는 문자열; `/reports/abc`가 500 대신 404). 대상 라우트 전수 목록(`current-map.md` 3절)을 계획에 기재.

## B-3 안전한 기본값
- `WEB_SECRET_KEY`가 없거나 32바이트 미만이면 개발 모드가 아닐 때 기동 실패(`webapp/app.py`의 `"local-development-only"` 기본값 제거). 개발 모드 판별 방법을 계획에 명시.
- `WEB_COOKIE_SECURE` 기본 true(로컬 compose에서만 false 명시), Helm `values.yaml`의 `cookieSecure` 기본값 true.
- `app/mailers/smtp_mailer.py` `validate()`: 사용자명이 있는데 TLS·SSL이 모두 꺼져 있으면 오류.

## B-4 로그인 보호와 세션 위생
1. **이메일 기준** 시도 제한부터: 로그인 전 `audit.authentication_logs`에서 최근 15분간 같은 이메일의 실패가 10회 이상이면 429 + 안내 화면(필요 인덱스는 추가형 마이그레이션).
2. **IP 기준 제한과 `ProxyFix`는 실제 신뢰 프록시 단계 수(ALB → ingress → pod 등)를 사용자가 확인한 뒤** 적용합니다. 확인 전에는 코드에 설정값(`TRUSTED_PROXY_HOPS`, 기본 0)만 두고 비활성.
3. 존재하지 않거나 비활성 계정도 모듈 수준 더미 argon2 해시로 검증해 응답 시간을 맞춤. 인증 로그에 `source_ip`(신뢰 프록시 설정 시)·`user_agent`, LOGOUT 기록.
4. 세션: `last_seen_at` 30분 유휴 만료, 로그인 시 기존 쿠키 세션 폐기, 비밀번호 재설정·`bootstrap-admin` 시 해당 사용자 세션 삭제, 로그인 성공 시 `check_needs_rehash`.
5. MFA는 범위 밖 — `docs/adr/`에 "MSP 역할 TOTP 도입" ADR 초안만.

## B-5 지표 시계열 저장 표현 정리 (D1: 수집 데이터 손실 금지)
**전제 정정(T00 조사)**: 시계열 소비자 3곳이 `raw.dps`(시각·값 쌍)를 직접 읽습니다 —
`app/report_analysis/metrics.py:277–299`, `app/renderers/html_renderer.py:3956–3963`, `database/report_repository.py:968–1042`.
분석은 AVG가 없으면 MIN→MAX 순으로 대체합니다(`metrics.py:185–197`). 반면 각 항목의 `values`는 `dps`의 값만 복사한 것이라 시각 정보가 없습니다.
따라서 **`raw`를 지우면 안 되고**, 줄일 대상은 같은 정보의 중복입니다.

1. **정규 시계열 접근자** 한 곳(예: `app/metric_series.py`)에 `series_points(entry) -> list[tuple[int, float]]`(epoch ms, 값)를 만듭니다.
   읽기 순서: 새 형식 `points` → 구형 `raw.dps` → 구형 `values`(시각 없음: 이 경우 시각 정보 없음으로 처리하고 현재 동작과 동일하게).
   정밀도는 원본 그대로(반올림 금지 — 반올림은 별도 결정 사항).
2. 소비자 3곳을 이 접근자로 전환합니다. **먼저** 구형 스냅샷 픽스처(현재 형식)로 각 소비자의 출력(분석 결과, 렌더 HTML, `metric_series` 행)을 골든으로 고정하고, 전환 후 동일함을 증명합니다.
3. 새 저장 형식: 정규화(`normalizers/insightmetricnormalizer.py:84–90`)가 통계별로 `{"points": [[ms, v], ...], "dimensions": {...}, "meta": {dps를 제외한 원본 필드}}`를 저장하고,
   중복인 `values`와 `raw.dps`는 저장하지 않습니다. MIN·AVG·MAX 세 통계는 **모두 유지**합니다(D1, 분석 대체 경로).
4. 스냅샷 조회 경량화(데이터 변경 없음):
   - `load_previous_report_snapshot`의 `jsonb_typeof(snapshot.normalized_data) = 'object'` 조건 제거(`report_repository.py:423` 부근), 필요한 키만 SELECT.
   - 과거 인프라 스냅샷 조회(`report_repository.py:104–196`)가 JSON 경로로 필터·정렬하는 부분은, 관측 시각을 실제 컬럼으로 두는 **추가형 마이그레이션**을 계획에 제안(적용 여부는 사용자 승인).
5. **기존 행 변환은 하지 않습니다.** 구형 행은 접근자의 폴백으로 계속 읽습니다. 변환은 해시·매니페스트 규약이 정해지는 T07에서 다룹니다.
- 완료: 구형·신형 스냅샷 모두에서 세 소비자 출력 동일(골든 테스트), 새 리포트 스냅샷 크기 전후 측정치, 점 개수·시각 일치 검증, 데이터 손실 0.

## B-6 커넥션 풀·요청 경량화 (새 의존성 — 승인 필요)
1. `psycopg[binary,pool]`(또는 `psycopg_pool`) 추가는 **사용자 승인 후**. 설치는 네트워크 단계.
2. **DB 역할별로 풀을 분리**하고(웹 MSP 역할, public/gov 워커 역할 등), 테넌트·환경 컨텍스트(`set_config(..., true)`, `report_repository.py:44`)가 트랜잭션 범위라
   반납 후 남지 않음을 테스트로 증명합니다(같은 연결을 다른 테넌트가 이어 쓰는 시나리오). 필요하면 반납 시 `RESET ALL`.
3. 연결 옵션 `statement_timeout`(웹 15초, 워커는 별도 값).
4. `before_request`에서 `static`, `health_live`, `health_ready`는 세션 조회 생략. `last_seen_at` UPDATE는 5분 이상 지났을 때만. 세션+사용자 컨텍스트 조회를 연결 1개로.
5. `SEND_FILE_MAX_AGE_DEFAULT` 장기 캐시 + `webapp/templates/base.html`의 모든 정적 URL에 버전 쿼리(현재 일부만 적용).

## B-7 네트워크 구성 중복 수집 제거 (같은 관측의 재사용만)
- `app/runner.py:691` 재사용 조건이 `LIVE_API_COLLECTION`일 때만이라 예약 실행에서 `collect_infrastructure()`를 다시 호출합니다(:714).
- **구분할 것**: (a) 과거 기간 표시에 쓰는 저장 스냅샷(`STORED_REPORT_SNAPSHOT`), (b) 이번 실행에서 새로 관측한 현재 인벤토리 백업(`runner.py:2027` 부근).
  재사용은 **(b)와 같은 실행 중에 이미 수집한 현재 관측분**에 한합니다. (a)를 새 실시간 관측본으로 저장하지 않습니다(`current-map.md` 5.2).
- Resource Manager 조회 생략 같은 **수집 축소는 하지 않습니다**(D1).
- 완료: 예약 실행 시나리오에서 같은 범주 목록 API가 한 실행 안에서 중복 호출되지 않음을 단언, 네트워크 구성 스냅샷의 내용·출처 표기 동일.

## B-8 작업 처리량·전역 동시성·재시도
1. 기존 큐 재시도(`webapp/jobs.py:255`: `max_attempts=3`, 지수 지연 상한 900초)를 **재사용**합니다. 새 재시도 체계를 만들지 않습니다.
2. 워커 1프로세스에 claim/처리 슬롯 `WORKER_CONCURRENCY`(기본 2). 슬롯별 DB 연결·API 팩토리 분리.
3. **전역 동시성 상한**은 슬롯과 별개입니다: claim 시 해당 환경의 `RUNNING` 작업 수가 `GLOBAL_MAX_RUNNING`(기본 3)을 넘으면 claim하지 않는 조건을 같은 트랜잭션에 넣습니다(SKIP LOCKED 유지). 계정별 동시 1건 제한도 함께.
4. 작업 하트비트: 실행 중 `locked_at` 주기 갱신 → `requeue_stale` 기준을 360분에서 하트비트 기반(예: 10분 무응답)으로. claim/fail 호출은 짧은 백오프 재시도로 감쌉니다.
5. HTTP 재시도(`utils/common_rest.py:475`): 타임아웃 `(connect=3.05, read=20)` 분리, 429의 `Retry-After` 준수, 백오프 풀 지터. 현행 재시도 대상(안전한 읽기 요청) 규칙은 유지.
6. 신규 일정의 기본 실행 분 분산은 T06에서 다룹니다(여기서는 하지 않음).
- 완료: 동시 투입 시 전역 상한·계정당 1건 준수 테스트, 하트비트 끊김 시 재큐 테스트, 재시도 단위 테스트.

## B-9 리포트 뷰어 겹침·상태 라벨 최소 정리
1. `webapp/static/automation.css:71`의 `.report-detail-shell{position:fixed; inset:0 0 0 250px}`이 720px 이하에서만 해제되어 721–1000px에서 메뉴 버튼과 브레드크럼을 덮음
   → 해제 중단점을 1000px로 맞추거나 셸을 `.main`의 일반 flex 자식으로.
2. **기존 헬퍼에서 시작**: `webapp/presentation.py`의 `format_status`(:58, Jinja 이름 `status_label`) 옆에 `status_tone`을 추가하고, `history.html:12` 등 템플릿 인라인 상태 판정을 교체합니다.
   이력 화면은 **보고서 상태(report_run.status)와 작업 상태(job.status)가 다른 축**입니다(`current-map.md` 5.3). 보고서가 있으면 보고서 상태, 없으면 작업 상태를 보여주고(이번에는 임시 단일 열 — T03에서 "작업"·"보고서 결과" 2열로 분리),
   `PARTIAL_SUCCESS`는 모든 화면에서 "부분 수집" + warn 톤. 원 코드는 `title` 속성에.
3. "재현하기" 링크 문구를 "보고서 보기"로(실제 재현은 T07).

## B-10 정책 결정 반영 (decisions.md)
- **D2**: `POST /reports/<report_id>/delete`의 실행에서 `protect_latest` 기본 **true**. 권한 집합은 유지. 최신 정상본 삭제 시 한국어 안내. 테스트: 운영자 단건 삭제 성공(최신 아님), 운영자·관리자 최신본 삭제 거부.
- **D3**: `app/report_options.py:8–69` CPU·메모리·디스크 warning/critical 하한 90 → **50**, `warning < critical` 서버 검증, 템플릿 `min`/`max`는 상수에서 출력, 기본값 90/95 유지,
  70% 미만은 저장 허용 + 안내. 테스트: 기존 고객 설정의 판정 결과 불변, 역전 값 거부, 경계값(50, 100).

## 공통 완료 조건
- [ ] 각 PR이 `ci/check.sh`(T00A) 통과, 새 테스트는 변경을 되돌리면 실패
- [ ] B-5: 데이터 손실 0, 구형 스냅샷 호환, 새 스냅샷 크기 측정치 첨부
- [ ] 네트워크 단계(B-1, B-6 설치)는 사용자 실행 결과 또는 승인 기록 첨부
- [ ] 보안 헤더·오류 페이지·로그인 제한은 로컬 compose에서 확인(운영 배포는 별도 승인)
