# T00B — 보안·성능 긴급 수정 (작고 효과 큰 것부터)

> 선행: T00A(최소 A-1·A-4). 근거: 2026-10-06 코드 점검 리포트 03·05·06절.
> 항목마다 **별도 PR**로 진행합니다. 각 PR은 테스트를 먼저 추가하고(현재 동작 고정 또는 실패 재현) 수정합니다.
> 표의 순서대로 진행하되, B-1·B-2·B-3은 하루 안에 끝낼 수 있는 크기입니다.

| PR | 내용 | 노력 |
|---|---|---|
| B-1 | cryptography 상한 해제 | S |
| B-2 | 보안 헤더 + 오류 페이지 + UUID 경로 | S |
| B-3 | 설정 누락 시 기동 실패(비밀키·쿠키) + SMTP 평문 로그인 차단 | S |
| B-4 | 로그인 시도 제한 + 계정 존재 시간차 제거 + 세션 위생 | M |
| B-5 | 스냅샷 원시 시계열 중복 저장 제거 + 기존 행 정리 | S–M |
| B-6 | DB 커넥션 풀 + 정적·헬스 요청 인증 제외 + 정적 캐시 | S–M |
| B-7 | 네트워크 구성 중복 수집 제거 | S |
| B-8 | 워커 다중 슬롯 + 재시도 지터·Retry-After + 타임아웃 분리 | S–M |
| B-9 | 리포트 뷰어 레이아웃 겹침 + 상태 라벨 단일화(최소판) | S |

---

## B-1 cryptography 상한 해제
- `requirements.in`: `cryptography>=50.0.0,<51` (사용처는 AES-GCM뿐: `webapp/security.py`, `utils/credentials.py` 등 T00에서 확인).
- 잠금 파일 재생성, 전체 테스트 + 자격증명 암·복호화 왕복 테스트, **기존에 암호화된 값이 새 버전에서 복호화되는지** 고정 픽스처로 확인.
- 완료: `pip-audit` 0건.

## B-2 보안 헤더·오류 페이지·UUID 경로
1. `webapp/app.py` 앱 팩토리에 `after_request` 훅:
   ```python
   response.headers.setdefault("X-Content-Type-Options", "nosniff")
   response.headers.setdefault("Referrer-Policy", "same-origin")
   response.headers.setdefault("X-Frame-Options", "DENY")          # 리포트 본문 라우트는 SAMEORIGIN 유지
   response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'; object-src 'none'; base-uri 'none'")
   if app.config["SESSION_COOKIE_SECURE"]:
       response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
   if g.get("user") and request.endpoint != "static":
       response.headers["Cache-Control"] = "no-store"
   ```
   `/reports/<id>/content`의 기존 CSP는 유지하되, 요청마다 파일을 읽어 모든 `<script>` 해시를 허용하는 방식(`portal_routes.py:305-314`)을
   **렌더러 스크립트 상수의 해시 1개**로 바꿉니다(과거 산출물 호환을 위해 산출물별 해시를 렌더 시 저장하는 방식도 허용 — 계획에 선택안 기재).
   iframe `sandbox`는 `portal.js`가 `contentDocument`에 접근하므로 이번 PR에서는 하지 않고 T08에서 postMessage 전환과 함께 처리.
2. 한국어 오류 템플릿 `errors/400.html`, `403.html`, `404.html`, `500.html`(앱 셸 없는 단순 레이아웃). 로그인 CSRF 실패(403)는 "세션이 만료되었습니다. 다시 로그인해 주세요." + 로그인 링크.
   XHR(`Accept: application/json`) 요청은 JSON 오류를 반환하고, 세션 만료 시 302 대신 **401 JSON** → `portal.js` 폴링은 401에서 중지.
3. ID 경로에 `<uuid:report_id>` 등 UUID 컨버터 적용(`/reports/abc` 같은 요청이 500이 아니라 404). 대상 라우트 전수 목록을 계획에 기재.
- 완료: 테스트로 헤더 존재, 오류 페이지 한국어, 잘못된 UUID 404, XHR 401 JSON 확인.

## B-3 안전한 기본값
- `WEB_SECRET_KEY`가 없거나 32바이트 미만이면, `APP_ENV != "development"`일 때 기동 실패(`webapp/app.py:40`의 기본값 제거).
- `WEB_COOKIE_SECURE` 기본값 true(로컬 compose에서만 false 명시). 세션 쿠키 이름에 `__Host-` 접두사(Secure·Path=/·Domain 없음 조건 충족 시).
- `app/mailers/smtp_mailer.py` `validate()`: 사용자명이 있는데 TLS·SSL 모두 꺼져 있으면 오류.
- `deploy/helm/ncp-report/values.yaml`의 `cookieSecure: false` 기본값을 true로(pilot은 이미 true).

## B-4 로그인 보호와 세션 위생
1. `werkzeug.middleware.proxy_fix.ProxyFix(app.wsgi_app, x_for=1, x_proto=1)` — ALB 뒤 실제 IP.
2. 로그인 전 `audit.authentication_logs`에서 최근 15분간 같은 이메일 또는 IP의 실패가 10회 이상이면 429 + "잠시 후 다시 시도" 화면. (외부 의존성 없이 기존 감사 테이블 사용, 필요 인덱스 추가 마이그레이션.)
3. 존재하지 않거나 비활성 계정도 모듈 수준 더미 argon2 해시로 검증해 응답 시간을 맞춤(`auth_routes.py:83`). 로그에 `source_ip`, `user_agent` 기록, LOGOUT 기록.
4. 세션: `last_seen_at` 30분 유휴 만료, 로그인 시 기존 쿠키의 세션 폐기, 비밀번호 재설정·`bootstrap_msp_admin` 시 해당 사용자 세션 전부 삭제, 로그인 성공 시 `check_needs_rehash`.
5. MFA는 이번 범위 아님 — `docs/adr/`에 "MSP 역할 TOTP 도입" ADR 초안만 작성.

## B-5 스냅샷 원시 시계열 중복 저장 제거 (재현성과 함께 고려)
배경: `database/report_repository.py:632`가 `report.server_metrics`를 통째로 스냅샷에 넣고, 여기에는 MIN·AVG·MAX별로 `values`와 원본 응답 전체(`"raw": item`,
`normalizers/insightmetricnormalizer.py:84-90`)가 들어 있어 **스냅샷의 99.9%**를 차지합니다(측정: 리포트 120건 150MB → 제거 후 392KB, 과거 인프라 조회 2.87초 → 18ms).
1. 정규화: `"raw": item` 제거(`values`와 차원만 유지). MIN/MAX는 전체 시계열 대신 요약값(min·max·발생 시각)만 보관.
2. **재현용 AVG 시계열은 유지**합니다(T07 재렌더의 원천). 값은 소수 2자리로 반올림해 저장.
3. 렌더러·분석이 MIN/MAX 전체 시계열을 쓰는 곳이 없는지 테스트로 확인(현재 렌더·분석·`metric_series`는 AVG만 사용).
4. `load_previous_report_snapshot`의 `jsonb_typeof(snapshot.normalized_data) = 'object'` 조건 제거(`report_repository.py:423`), 필요한 키만 SELECT.
5. 기존 행 정리 스크립트 `<cli> maintenance strip-raw-metrics --dry-run|--apply`: 배치 단위로 `normalized_data`에서 `raw`·MIN/MAX 시계열 제거,
   `content_hash_sha256` 재계산, 처리 건수·절감 용량 출력. 적용 후 `VACUUM (FULL)`은 점검 시간에 수동 실행하도록 런북에 기록.
- 완료: 새 리포트 스냅샷 크기 전후 비교, 기존 리포트가 모두 정상 표시, 드라이런 출력 첨부.

## B-6 커넥션 풀·요청 경량화
1. `psycopg[binary,pool]` + 프로세스당 `ConnectionPool(min_size=1, max_size=8)`. `webapp/repository.py`, `webapp/jobs.py`, `database/report_repository.py`의
   `psycopg.connect()` 호출을 풀에서 빌리도록 공용 헬퍼 하나(`database/pool.py`)로. 테넌트 `set_config(..., true)`는 트랜잭션 범위라 풀과 호환.
2. 연결 옵션에 `statement_timeout=15000`(워커는 별도 값).
3. `before_request`에서 `static`, `health_live`, `health_ready` 엔드포인트는 세션 조회 생략. `last_seen_at` UPDATE는 5분 이상 지났을 때만. 세션+사용자 컨텍스트를 연결 1개·쿼리 1~2개로.
4. `SEND_FILE_MAX_AGE_DEFAULT = 31536000` + 모든 정적 URL에 `?v={{ app_version }}`.
- 완료: `/notifications` 1회 요청의 연결 수(현재 3) → 0~1(풀 재사용), 응답 시간 전후 측정 첨부.

## B-7 네트워크 구성 중복 수집 제거
- `app/runner.py:691-694`의 재사용 조건이 `LIVE_API_COLLECTION`일 때만이라 예약 실행에서는 `collect_infrastructure()`를 다시 호출(714행).
  앞 단계에서 수집한 실시간 인벤토리(수집 완료 시각 포함)를 `resource_result`에 보관해 재사용하고, 네트워크 범주만 필요할 때 Resource Manager 조회를 생략.
- 완료: 예약 실행 시나리오 테스트에서 `InfrastructureCollector.collect` 호출 1회 단언(현재 2회).

## B-8 작업 처리량과 재시도
1. 워커 1프로세스에 claim/처리 슬롯 `WORKER_CONCURRENCY`(기본 3) — 스레드별 DB 연결·API 팩토리, `SKIP LOCKED`라 중복 실행 없음. claim/fail 호출은 백오프 재시도로 감싸기.
2. 작업 하트비트 스레드가 `locked_at` 갱신 → `requeue_stale` 기준을 360분에서 하트비트 기준(예: 10분 무응답)으로.
3. `utils/common_rest.py` 재시도: 타임아웃 `(3.05, 20)`, 429의 `Retry-After` 준수, 백오프 `random.uniform(0, 2**attempt)`(풀 지터), 작업 단위 마감 시간 컨텍스트.
4. 신규 일정 기본 실행 분을 09:00 고정 대신 계정별 결정적 분산(T06 지터 알고리즘의 최소판)으로. 기존 일정은 변경하지 않음.
- 완료: 8개 작업 동시 투입 시 처리 시간 전후 비교(모의 API), 재시도 단위 테스트.

## B-9 리포트 뷰어 겹침·상태 라벨 최소판
1. `.report-detail-shell{position:fixed; inset:0 0 0 250px}`(`automation.css:71-81`)이 720px 이하에서만 해제되어 721–1000px에서 메뉴 버튼과 브레드크럼을 덮음
   → 해제 중단점을 1000px로 맞추거나 셸을 `.main`의 일반 flex 자식으로.
2. `history.html:12`의 `'ok' if job_status in ('SUCCESS','PARTIAL_SUCCESS')` 등 템플릿 인라인 상태 판정을 기존 `status_label`(`webapp/presentation.py:58-64`)과
   새 `status_tone` 필터로 교체(전체 라벨 카탈로그는 T01). `PARTIAL_SUCCESS`는 모든 화면에서 "부분 수집" + warn 톤.
3. "재현하기" 링크 문구를 "보고서 보기"로(실제 재현은 T07).

## 공통 완료 조건
- [ ] 각 PR이 `ci/check.sh` 통과, 새 테스트는 변경을 되돌리면 실패
- [ ] B-5 이후 새 리포트 스냅샷이 이전 대비 90% 이상 작아짐(측정치 첨부)
- [ ] 보안 헤더·오류 페이지·로그인 제한이 운영 배포 전 스테이징(또는 로컬 compose)에서 확인됨
