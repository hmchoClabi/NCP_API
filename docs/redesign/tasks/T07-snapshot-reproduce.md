# T07 — 수집 스냅샷 분리와 재현(Reproduce) 기능

> 선행: T06. T00 5–7절(수집·분석·렌더 흐름, 재현성 저해 요소 목록)이 출발점입니다.
> 가장 위험도가 큰 작업입니다. **두 개의 PR로 나눕니다**: 7-A 저장 구조·매니페스트, 7-B 재현 기능·UI.
> 관리 명령은 `python -m webapp.cli`입니다(새 하위 명령은 argparse에 최소 연결).

## 현행 반영 (T00 결과·결정, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **기존 것을 재사용**: `{env}_data.report_snapshots`, `network_configuration_snapshots`, `metric_series`, `ReportResult.from_dict`,
  분석 버전 상수 `ANALYSIS_VERSION = "1.3"`(`app/report_analysis/engine.py:23`). 분석 버전 상수는 새로 만들지 않습니다. 렌더러 버전 상수만 신설합니다.
- **버전 축을 섞지 않습니다**: 스냅샷 스키마 버전(현재 SQL 리터럴 `'1.5'`, `database/report_repository.py:548, 640`), 설정 JSON `schema_version`(1.4),
  코드 버전(`RENDERER_VERSION`, `ANALYSIS_VERSION`, collector/normalizer)은 서로 다른 축입니다. 버전 컬럼에 실제 코드 버전을 기록하도록 고치되, 기존 행의 `'1.5'`는 "스키마 1.5 시절 기록"으로 해석합니다.
- **기준(baseline) 고정**: 큐에 넣는 시점의 유효 설정 전체(T05 `settings_snapshot`)뿐 아니라 비교 기준 보고서(`baseline_report_run_id`)와 그 해시,
  청구 집계 기준(조회 기간·집계 시각·할인/VAT 기준)을 매니페스트에 고정합니다. 현재 options JSON은 저장되지만 큐 시점의 불변 기준 전체를 고정하지는 않습니다.
- **정규 해시**: 설정·스냅샷·매니페스트 해시는 `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`의 sha256으로 통일합니다(한 함수).
- **네트워크 스냅샷 결합**: Route Table·ACG·NACL 규칙은 `network_configuration_snapshots`에 따로 있습니다. 재현 입력 = `report_snapshots` + `network_configuration_snapshots` + 필요한 `metric_series`이며,
  매니페스트에 각각의 해시를 기록합니다. `report_snapshots`만으로 복원된다고 가정하지 않습니다.
- **원천 데이터 보존 키**: `tenant_report_settings.settings` JSON에 추가 키(`snapshot_retention_policies.{DAILY,WEEKLY,MONTHLY}`, 형식은 기존 `retention_policies`와 같음)로 둡니다. 별도 테이블 금지.
- **삭제·정리와 CASCADE**: 현재 보고서 삭제는 FK `ON DELETE CASCADE`로 스냅샷·지표·이벤트를 함께 지우고, 파일은 `artifact_cleanup_outbox`로 지웁니다.
  원천 데이터 보존을 분리하려면 CASCADE 관계와 정리 코드(`webapp/repository.py:2374` 후보 계산, `delete_report` :3128 실행 시 재검사, `webapp/artifact_cleanup.py`)를 **함께** 바꿔야 합니다.
  이미 삭제된 보고서를 "재현 가능"으로 안내하지 않습니다.
- **`LEGAL_HOLD`는 신규 보호 사유**입니다. 정리 후보 계산·실행 시 재검사·화면(01-design-system.md 5.2 `cleanup` kind)에 함께 추가합니다.
- **기존 파일 경로 보존**: 기존 산출물 경로(`<output>/<customer>/<account>/<job>/<customer>/ncp_report_*.html|json`, current-map 7.1)와 보관 HTML은 옮기지 않습니다. 새 경로는 새 버전에만 씁니다.
- **스냅샷 저장 매체**: 현재 스냅샷은 DB(JSONB)에 있습니다. 파일(`jsonl.zst`)로 옮길지 DB에 둘지는 계획에서 용량·백업·RLS·트랜잭션 측면을 비교해 제안하고 승인받습니다.
- T00B-5에서 미룬 **구형 metric 행 변환**(`raw.dps` → `points`)은 이 작업에서 선택적으로 할 수 있습니다(멱등·`--dry-run`·건수 보고, 결정 D1: 시각·값·차원 손실 금지).

## 목표
"한 번 작성된 리포트는 보관하고, 재실행 시 기존에 생성된 데이터를 이용해 재현"할 수 있게 합니다.

현재는
- 보고서 HTML 산출물에 `<meta name="report-id">` 외에 **어떤 데이터·설정·템플릿으로 만들었는지 기록이 없고**,
- `/history`의 "재현하기"는 **보고서 보기 링크일 뿐**이며,
- 보고서를 지우면 "관련 수집 데이터"도 함께 지워져 원천 데이터와 산출물의 보존을 따로 관리할 수 없습니다.

## 개념

```
수집(Collect) ──► 스냅샷(불변) ──► 분석(Analyze) ──► 렌더(Render) ──► 산출물(HTML) + manifest
                    ▲                                                  │
                    └──────────── 재현은 여기서부터 다시 ◄─────────────┘
```

| 동작 | 외부 API 호출 | 입력 | 결과 |
|---|---|---|---|
| **원본 보기** | 없음 | 저장된 산출물 | 그대로 표시 |
| **재현 검증** | 없음 | 같은 스냅샷 + 같은 설정 스냅샷 + **같은 `RENDERER_VERSION`** | 다시 렌더한 해시를 원본과 비교 → `VERIFIED` / `DIFFERS` / `UNAVAILABLE` |
| **최신 템플릿으로 재생성** | 없음 | 같은 스냅샷 + 현재 설정(또는 원본 설정) + 현재 렌더러 | 같은 보고서의 **새 버전** |
| **재수집** | 있음 | 같은 보고 기간으로 새 수집 | 새 스냅샷 + 새 버전 (예: 월간 확정 청구 반영) |

### 렌더러 버전
- 빌드 번호와 별개인 **의미 있는 버전 상수** `RENDERER_VERSION = "2.0.0"`(semver)을 렌더러 모듈에 둡니다.
  출력 HTML이 1바이트라도 달라지는 변경이면 올리고 `CHANGELOG-renderer.md`에 기록합니다. 분석 로직은 **기존** `ANALYSIS_VERSION`(현재 `"1.3"`, `app/report_analysis/engine.py:23`)을 같은 규칙으로 관리합니다(새 상수 금지).
- 재현 검증은 저장된 `renderer_version == RENDERER_VERSION`이고 `analysis_version == ANALYSIS_VERSION`일 때만 수행합니다.
  다르면 `UNAVAILABLE`(사유: "렌더러 버전이 달라 동일 조건 재현 불가 — 최신 템플릿으로 재생성은 가능") 을 기록합니다.
  과거 렌더러를 보관해 실행하는 것은 이번 범위가 아닙니다.

## 7-A. 저장 구조와 매니페스트

> **기존 테이블을 먼저 확장하세요.** 이미 `{public,gov}_data.report_snapshots`(`schema_version`, `normalized_data` JSONB, `content_hash_sha256`,
> `collector_version`·`normalizer_version`·`renderer_version` 컬럼)와 `network_configuration_snapshots`, `metric_series`가 있습니다.
> 단, 버전 컬럼은 SQL 리터럴 `'1.5'`로 고정 저장되고(`database/report_repository.py:548, 640`), 저장되는 내용은 정규화·분석 결과이며(범주 표시 필터는 렌더 시 `display_infrastructure`로 적용, 수집 원본은 유지 — D1),
> `ReportResult.from_dict`는 운영 코드에서 호출되지 않습니다. 아래 `collection_snapshot`·`report_version`은 개념 모델입니다.
> 기존 테이블에 컬럼을 추가해 같은 의미를 낼 수 있으면 그 방식을 우선하고, 새 테이블이 필요하면 계획에서 이유를 설명하세요.
> 새 테이블은 환경별 스키마(`public_data`/`gov_data`) 배치와 RLS 정책을 따릅니다. T00B-5(원시 시계열 정리) 이후에 진행합니다.

### 데이터 모델
```
collection_snapshot                    -- 불변
  id (uuid) · tenant_id · account_id · period_start · period_end
  report_type (00-context 11절 열거형) · collector_version · created_by_job_id
  started_at · finished_at · status (SUCCESS | PARTIAL_SUCCESS | FAILED)
  storage_uri · format ('jsonl.zst' 권장, 불가 시 'json.gz') · size_bytes · sha256
  sources (json: [{source:"cloud_insight.events", params_hash, fetched_at, record_count, status, error_code}])
  retention_class (STANDARD | LONG | LEGAL_HOLD) · expires_at (nullable)
  legal_hold_reason · legal_hold_by · legal_hold_at

report_version                         -- 보고서 1건에 여러 버전
  id · report_id · version (int) · job_id (이 버전을 만든 작업) · snapshot_id (nullable)
  render_mode (ORIGINAL | RERENDER_LATEST | RECOLLECT)
  reproducible (bool)        -- 스냅샷과 설정 스냅샷이 모두 있어야 true
  settings_snapshot (jsonb)  -- T05 report_jobs.settings_snapshot 을 그대로 복사
  baseline_report_run_id · baseline_sha256 · network_snapshot_id · network_snapshot_sha256
  profile_id · profile_version · renderer_version · analysis_version · template_hash
  rendered_at                -- 렌더 코드에서 now() 대신 이 값을 사용
  artifact_uri · artifact_sha256 · artifact_size_bytes
  parent_version_id · created_by · created_at · note
  UNIQUE(report_id, version)

report_runs (기존) + current_version_id
report_jobs (기존) + job_type (COLLECT_AND_RENDER | RERENDER | RECOLLECT | VERIFY, 신규 컬럼·CHECK — 기존 행은 COLLECT_AND_RENDER로 간주) + report_version_id (결과)

reproduction_check
  id · report_version_id · job_id · checked_at · result (VERIFIED | DIFFERS | UNAVAILABLE)
  new_sha256 · diff_summary · reason
```
- 재생성·재수집·재현 검증은 모두 **작업(`report_jobs`) 행을 만들고 비동기로 실행**합니다. 실행 이력에 함께 나타납니다.

### 저장 경로 (새 버전에만 적용, `REPORT_OUTPUT_DIR` 기준 — 기존 경로와 충돌하지 않게)
```
{REPORT_OUTPUT_DIR}/snapshots/{tenant_id}/{account_id}/{yyyy}/{mm}/{snapshot_id}.jsonl.zst   # 파일 저장을 승인받은 경우만
{REPORT_OUTPUT_DIR}/artifacts/{tenant_id}/{report_id}/v{version}/report.html
{REPORT_OUTPUT_DIR}/artifacts/{tenant_id}/{report_id}/v{version}/manifest.json
```
`manifest.json` 예:
```json
{
  "report_id": "…", "version": 2, "render_mode": "RERENDER_LATEST", "job_id": "…",
  "snapshot": {"id": "…", "sha256": "…", "collector_version": "1.8.0", "period_start": "2026-09-30T00:00:00+09:00", "period_end_exclusive": "2026-10-01T00:00:00+09:00"},
  "network_snapshot": {"id": "…", "sha256": "…"},
  "settings": {"profile_id": "…", "profile_version": 5, "schema_version": "1.4", "sha256": "…"},
  "baseline": {"report_run_id": "…", "sha256": "…"},
  "billing_context": {"query_period": ["2026-09-01", "2026-09-30"], "aggregated_at": "…", "basis": "…"},
  "snapshot_schema_version": "1.5", "renderer_version": "2.0.0", "analysis_version": "1.3", "template_hash": "…",
  "rendered_at": "2026-10-01T09:07:12+09:00",
  "artifact_sha256": "…"
}
```
산출물 HTML `<head>`에도 `<meta name="report-version">`, `<meta name="snapshot-sha256">`, `<meta name="renderer-version">`를 넣습니다.

### 결정성 확보
T00 6절의 저해 요소를 모두 제거합니다.
- 렌더·분석 코드에서 현재 시각 호출 금지 → `context.rendered_at` 주입.
- dict/set 순회는 키 정렬, 목록은 명시적 정렬 키(동률 시 id).
- 렌더 중 난수·UUID 생성 금지(DOM id는 데이터 키로 결정적 생성).
- 로케일·시간대 고정(`Asia/Seoul`), 숫자 포맷 함수 고정.
- 인라인 CSS/JS는 렌더러 패키지 안 정적 파일에서 읽고, 그 해시를 `template_hash`에 반영.
- 테스트: 같은 스냅샷·설정·`rendered_at`으로 두 번 렌더 → **바이트 단위 동일**.

### 기존 데이터 마이그레이션
- 기존 보고서마다 `report_version v1 (ORIGINAL)` 생성, 기존 산출물 경로를 그대로 가리킴(파일 이동은 선택, 이동 시 원자적 rename + sha256 검증).
- 기존 "관련 수집 데이터"가 재사용 가능한 형태면 `collection_snapshot`으로 등록(sha256 계산), 아니면 `snapshot_id = null`, `reproducible = false`.
- T05에서 `report_jobs`에 저장한 `settings_snapshot`·`profile_id`·`profile_version`을 `report_version`으로 복사. T05 이전 보고서는 설정 스냅샷이 없으므로 `reproducible = false`.
- 마이그레이션은 **멱등**, `--dry-run`으로 대상 건수·용량·재현 가능 비율을 먼저 출력.

### 보존·정리·삭제 규칙
- **보존 정책 분리**: `tenant_report_settings.settings`에 원천 데이터 보존 키 `snapshot_retention_policies`(형식은 기존 `retention_policies`와 같음)를 추가합니다(산출물은 기존 `retention_policies`).
  - `FOREVER` → `retention_class = LONG`, `expires_at = null` / `DAYS` → `STANDARD`, `expires_at = 생성일 + days`.
  - 산출물은 스냅샷이 있으면 다시 만들 수 있으므로 더 짧게 둘 수 있습니다. 고객 워크스페이스 › 출력 설정 › 보존 정책 UI를 "산출물 / 원천 데이터" 2열로 바꿉니다.
- **법적 보존(LEGAL_HOLD, 신규 보호 사유)**: `MSP_ADMIN`만 설정·해제. 보고서 뷰어 `⋯ › 법적 보존` → 사유 입력. 해당 보고서의 모든 버전이 참조하는 스냅샷에 적용. 어떤 정리·삭제에서도 제외.
- **스냅샷 중복 제거는 하지 않습니다.** 스냅샷 1건은 수집 1회에 대응합니다(참조 관계 단순화).
- **보고서 삭제**: 해당 보고서의 모든 버전 산출물 삭제. 스냅샷은 **다른 `report_version`이 참조하지 않고 LEGAL_HOLD가 아닐 때만** 삭제(현행 CASCADE 변경 필요, 위 현행 반영 절). 결정 D2의 최신 정상본 보호는 유지. 확인 대화상자에 삭제될 버전 수·스냅샷 수·용량 표시.
- **데이터 정리 화면**: "산출물만 정리(재생성 가능)" / "원천 데이터까지 정리(재현 불가)" 두 모드. 후자는 참조 검사 후 타이핑 확인.

## 7-B. 재현 기능과 UI

### 엔드포인트 (상태 변경은 모두 POST + CSRF, 비동기 작업)
- `POST /reports/{id}/versions/{v}/verify` → VERIFY 작업
- `POST /reports/{id}/rerender` (form: `settings=current|original`, `note`) → RERENDER 작업 → 새 버전
- `POST /reports/{id}/recollect` (form: `note`) → RECOLLECT 작업 → 새 스냅샷 + 새 버전
- `GET /reports/{id}/versions` → 버전 목록 (HTML 부분 템플릿 + JSON)
- `GET /reports/{id}/versions/{v}` → 특정 버전 뷰어, `GET /reports/{id}/versions/{v}/content` → 특정 버전 본문
  (`/reports/{id}`, `/reports/{id}/content`는 `current_version`을 보여주는 기존 동작 유지)
- `GET /reports/{id}/versions/{a}/diff/{b}` → 섹션별 요약 diff(판정 변화, 금액 변화, 자원 수 변화)

### 월간 확정 청구 연동 (T06에서 이월)
- 일정 컬럼 `publish_estimate_first` (bool, 기본 false) 추가.
- true이면 `BILLING_FINALIZED` 대기 없이 추정 데이터로 먼저 v1 발행 → 확정 데이터 확인 시 **자동 RECOLLECT** 작업으로 v2 생성(`note="확정 청구 반영"`), 알림함 알림.

### 보고서 뷰어
- 툴바에 **버전 선택기**(`v3 · 최신 템플릿 재생성 · 10-01 10:12 ▾`), 기본은 `current_version`.
- **출처 패널**(사이드 시트 "이 보고서의 근거"): 스냅샷 기간·수집 시각·소스별 상태와 건수, 설정 프로필·버전, 렌더러·분석 버전, 해시, 재현 검증 이력, 공유 링크 목록(T06).
- 동작(`⋯`): `재현 검증` · `최신 템플릿으로 재생성` · `재수집` · `버전 비교` · `법적 보존`. 각 항목 설명에 외부 API 호출 여부 명시.
- `reproducible = false` 버전: 재현 검증 비활성 + "이 버전은 원천 데이터 또는 설정 기록이 없어 재현할 수 없습니다" 안내(재수집은 가능).

### 다른 화면에 켜기 (앞 단계에서 미뤄 둔 항목)
- `/portal` 보고서 보관함(T03): **버전 열** 표시(`v3`), 필터 "재현 가능만", 행 `⋯`에 `재현 검증`·`재수집` 추가.
- `/history` 실행 이력: T00B-9에서 "보고서 보기"로 바꾼 링크를 행 `⋯`로 옮기고 `재현 검증`·`재수집` 추가. 작업 유형 배지(`job_type`)와 `render_mode` 배지 표시.
- 고객 워크스페이스 › 출력 설정 › 표시 범위(T04): 범주별 "최근 수집 시 N개 발견"을 **최근 스냅샷**에서 집계하도록 교체.
- 고객 워크스페이스 › 출력 설정 미리보기(T04): 목차 요약에서 저장된 스냅샷 재렌더 미리보기로 확장.

## 완료 조건
- [ ] 7-A: 신규 생성 보고서마다 스냅샷 1건 + 버전 1건 + manifest.json, sha256 일치
- [ ] 7-A: 매니페스트에 baseline·네트워크 스냅샷·설정 해시가 정규 해시 함수로 기록되고, 스냅샷 스키마·설정 스키마·코드 버전이 서로 다른 필드로 기록됨
- [ ] 7-A: 결정성 테스트(동일 입력 2회 렌더 바이트 동일) 통과, T00 6절 저해 요소 전부 해소 표시
- [ ] 7-A: 기존 보고서 마이그레이션 드라이런·실행 결과(건수·재현 가능 비율) 첨부, 기존 보고서 전부 정상 열림
- [ ] 7-A: 보고서 삭제·정리 시 다른 버전이 참조하는 스냅샷과 LEGAL_HOLD 스냅샷이 남는다는 테스트(정리 후보 계산·실행 시 재검사 모두)
- [ ] 7-A: 마이그레이션 추가형·빈 DB 2회 적용·기존 데이터 위 적용 성공, 전진 수정 계획 첨부
- [ ] 7-B: 재현 검증·재생성이 외부 API를 호출하지 않음(네트워크 목킹으로 호출 0회 단언)
- [ ] 7-B: 재생성·재수집이 새 버전을 만들고 원본 버전 산출물 바이트는 변하지 않음
- [ ] 7-B: 렌더러 버전이 다른 버전에 대한 검증이 `UNAVAILABLE`과 사유를 기록
- [ ] 7-B: 버전별 URL, 버전 diff, 출처 패널, 재현 불가 안내, `/portal`·`/history`·표시 범위 화면 반영
- [ ] 7-B: `publish_estimate_first` 시나리오(추정 v1 → 확정 v2) 테스트

## 검증
- `python -m webapp.cli reports verify --sample 20`: 최근 보고서 20건 재현 검증 후 일치율 출력. 결과 첨부.
- 저장공간 영향 추정: 스냅샷 평균 크기 × 일정 수 × 보존 일수 계산표 첨부(운영 PVC 실제 용량은 미확인 — 9.75GiB 관측값과 Helm 기본 20Gi를 함께 놓고 계산).
