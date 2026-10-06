# T07 — 수집 스냅샷 분리와 재현(Reproduce) 기능

> 선행: T06. T00 5–7절(수집·분석·렌더 흐름, 재현성 저해 요소 목록)이 출발점입니다.
> 가장 위험도가 큰 작업입니다. **두 개의 PR로 나눕니다**: 7-A 저장 구조·매니페스트, 7-B 재현 기능·UI.
> `<cli>`는 T00에서 확인한 관리 명령 진입점으로 바꿔 쓰세요.

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
  출력 HTML이 1바이트라도 달라지는 변경이면 올리고 `CHANGELOG-renderer.md`에 기록합니다. 분석 로직도 `ANALYSIS_VERSION`으로 동일하게.
- 재현 검증은 저장된 `renderer_version == RENDERER_VERSION`이고 `analysis_version == ANALYSIS_VERSION`일 때만 수행합니다.
  다르면 `UNAVAILABLE`(사유: "렌더러 버전이 달라 동일 조건 재현 불가 — 최신 템플릿으로 재생성은 가능") 을 기록합니다.
  과거 렌더러를 보관해 실행하는 것은 이번 범위가 아닙니다.

## 7-A. 저장 구조와 매니페스트

> **기존 테이블을 먼저 확장하세요.** 이미 `{public,gov}_data.report_snapshots`(`schema_version`, `normalized_data` JSONB, `content_hash_sha256`,
> `collector_version`·`normalizer_version`·`renderer_version` 컬럼)와 `network_configuration_snapshots`, `metric_series`가 있습니다.
> 단, 버전 컬럼은 SQL 리터럴 `'1.5'`로 고정 저장되고(`database/report_repository.py:548, 640`), 저장되는 내용은 옵션 필터·분석 이후 결과이며,
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
  settings_snapshot (json)   -- T05 report_job.settings_snapshot 을 그대로 복사
  profile_id · profile_version · renderer_version · analysis_version · template_hash
  rendered_at                -- 렌더 코드에서 now() 대신 이 값을 사용
  artifact_uri · artifact_sha256 · artifact_size_bytes
  parent_version_id · created_by · created_at · note
  UNIQUE(report_id, version)

report (기존) + current_version_id
report_job (기존) + job_type (COLLECT_AND_RENDER | RERENDER | RECOLLECT | VERIFY) + report_version_id (결과)

reproduction_check
  id · report_version_id · job_id · checked_at · result (VERIFIED | DIFFERS | UNAVAILABLE)
  new_sha256 · diff_summary · reason
```
- 재생성·재수집·재현 검증은 모두 **작업(report_job) 행을 만들고 비동기로 실행**합니다. 실행 이력에 함께 나타납니다.

### 저장 경로 (PVC, T00 7절의 기존 레이아웃과 충돌하지 않게 조정)
```
/data/snapshots/{tenant_id}/{account_id}/{yyyy}/{mm}/{snapshot_id}.jsonl.zst
/data/artifacts/{tenant_id}/{report_id}/v{version}/report.html
/data/artifacts/{tenant_id}/{report_id}/v{version}/manifest.json
```
`manifest.json` 예:
```json
{
  "report_id": "…", "version": 2, "render_mode": "RERENDER_LATEST", "job_id": "…",
  "snapshot": {"id": "…", "sha256": "…", "collector_version": "1.8.0", "period": ["2026-09-30T00:00:00+09:00","2026-09-30T23:59:59+09:00"]},
  "settings": {"profile_id": "…", "profile_version": 5, "sha256": "…"},
  "renderer_version": "2.0.0", "analysis_version": "2.1.0", "template_hash": "…",
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
- T05에서 `report_job`에 저장한 `settings_snapshot`·`profile_id`·`profile_version`을 `report_version`으로 복사. T05 이전 보고서는 설정 스냅샷이 없으므로 `reproducible = false`.
- 마이그레이션은 **멱등**, `--dry-run`으로 대상 건수·용량·재현 가능 비율을 먼저 출력.

### 보존·정리·삭제 규칙
- **보존 정책 분리**: T04의 `customer_retention_policy`에 `snapshot_mode`·`snapshot_days` 컬럼을 추가합니다(산출물 컬럼은 기존 것을 사용).
  - `FOREVER` → `retention_class = LONG`, `expires_at = null` / `DAYS` → `STANDARD`, `expires_at = 생성일 + days`.
  - 산출물은 스냅샷이 있으면 다시 만들 수 있으므로 더 짧게 둘 수 있습니다. 고객 워크스페이스 › 출력 설정 › 보존 정책 UI를 "산출물 / 원천 데이터" 2열로 바꿉니다.
- **법적 보존(LEGAL_HOLD)**: MSP 관리자만 설정·해제. 보고서 뷰어 `⋯ › 법적 보존` → 사유 입력. 해당 보고서의 모든 버전이 참조하는 스냅샷에 적용. 어떤 정리·삭제에서도 제외.
- **스냅샷 중복 제거는 하지 않습니다.** 스냅샷 1건은 수집 1회에 대응합니다(참조 관계 단순화).
- **보고서 삭제**: 해당 보고서의 모든 버전 산출물 삭제. 스냅샷은 **다른 `report_version`이 참조하지 않고 LEGAL_HOLD가 아닐 때만** 삭제. 확인 대화상자에 삭제될 버전 수·스냅샷 수·용량 표시.
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
- `/history` 실행 이력: "재현하기" 링크 제거 → 행 `⋯`에 `보고서 보기`·`재현 검증`·`재수집`. 작업 유형 배지(`job_type`)와 `render_mode` 배지 표시.
- 고객 워크스페이스 › 출력 설정 › 수집 범위(T04): 범주별 "최근 수집 시 N개 발견"을 **최근 스냅샷**에서 집계하도록 교체.

## 완료 조건
- [ ] 7-A: 신규 생성 보고서마다 스냅샷 1건 + 버전 1건 + manifest.json, sha256 일치
- [ ] 7-A: 결정성 테스트(동일 입력 2회 렌더 바이트 동일) 통과, T00 6절 저해 요소 전부 해소 표시
- [ ] 7-A: 기존 보고서 마이그레이션 드라이런·실행 결과(건수·재현 가능 비율) 첨부, 기존 보고서 전부 정상 열림
- [ ] 7-A: 보고서 삭제·정리 시 다른 버전이 참조하는 스냅샷과 LEGAL_HOLD 스냅샷이 남는다는 테스트
- [ ] 7-B: 재현 검증·재생성이 외부 API를 호출하지 않음(네트워크 목킹으로 호출 0회 단언)
- [ ] 7-B: 재생성·재수집이 새 버전을 만들고 원본 버전 산출물 바이트는 변하지 않음
- [ ] 7-B: 렌더러 버전이 다른 버전에 대한 검증이 `UNAVAILABLE`과 사유를 기록
- [ ] 7-B: 버전별 URL, 버전 diff, 출처 패널, 재현 불가 안내, `/portal`·`/history`·수집 범위 화면 반영
- [ ] 7-B: `publish_estimate_first` 시나리오(추정 v1 → 확정 v2) 테스트

## 검증
- `<cli> reports verify --sample 20`: 최근 보고서 20건 재현 검증 후 일치율 출력. 결과 첨부.
- 저장공간 영향 추정: 스냅샷 평균 크기 × 일정 수 × 보존 일수 계산표 첨부(PVC 9.75GiB 기준 여유 확인).
