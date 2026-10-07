# T05 — 리포트 프로필 (재사용 가능한 보고서 구성 템플릿 + 버전 관리)

> 선행: T04. 스키마 변경 폭이 큰 작업입니다. 계획 단계에서 스키마와 기존 설정 변환 규칙을 먼저 승인받으세요.
> 보고서 유형 값은 `00-context.md` 11절 열거형을 따릅니다.

## 현행 반영 (T00 결과·결정, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **유형 값**: 현행 `CUSTOM`을 씁니다(예전 설계의 `RANGE` = `CUSTOM`). 프로필 대상 유형은 `DAILY | WEEKLY | MONTHLY | CUSTOM | ANY`.
- **새 테이블 배치**: `control` 스키마에 두고, `tenants`·`cloud_accounts`와의 FK는 기존 복합 키(`cloud_accounts`의 `(id, tenant_id)` unique)를 활용해 고객·계정·환경이 어긋나지 않게 합니다.
  **RLS 정책·역할별 GRANT**를 기존 control 테이블과 같은 방식으로 붙입니다. 프로필은 전 고객 공용이므로 MSP 역할만 쓰기, 고객 사용자는 접근 불가.
- **마이그레이션은 forward-only**입니다. 본문의 "업/다운"은 폐기하고 AGENTS.md 5절 6번(추가형, 빈 DB 2회 적용, 기존 데이터 위 적용, 전진 수정 계획)으로 검증합니다.
  새 SQL은 `database/schema/`의 다음 번호(현재 마지막 210)로, `IF NOT EXISTS` 등으로 재실행 안전하게 씁니다.
- **변환 원본**은 T04가 확장한 `tenant_report_settings.settings` JSON(유형별 키 포함)입니다. 변환 후에도 각 고객·계정·유형의 **섹션·순서·표시 범위·분석 임계치·브랜딩** 결과가 같아야 합니다(전수 비교 스크립트).
- **보존 정책**은 계속 `tenant_report_settings.settings.retention_policies`에 둡니다(프로필에 넣지 않음). 로고는 `tenant_branding`에 그대로 두고 프로필은 `branding.logo = "tenant"` 참조만 합니다.
- **작업 기록**: `report_jobs`에 `profile_id`·`profile_version`·`settings_snapshot`을 nullable 컬럼으로 추가합니다. 큐에 넣는 시점에 확정한 유효 설정을 저장합니다.
- **결정 D1**: settings JSON에서 범주 선택은 `display_scope`(표시 범위), WMS·Security Monitoring 수집 토글은 `collection_options`로 분리합니다.
- **권한**: 프로필 편집은 `MSP_ADMIN`, 조회·적용은 `MSP_OPERATOR`까지. `SYSTEM_ADMIN`은 현행 라우트 권한 규칙을 따릅니다(자동 동등 취급 금지).

## 목표
고객이 늘어날수록 고객마다 섹션·범주·임계치를 하나씩 맞추는 방식은 유지가 어렵습니다.
**프로필**(예: "공공 표준 일일", "민간 경영진 월간")을 만들어 여러 고객·계정에 적용하고, 고객별로 필요한 항목만 덮어쓰게 합니다.
프로필과 고객 설정은 **버전 관리**되어, 보고서가 어떤 설정으로 만들어졌는지 언제든 복원할 수 있어야 합니다(T07 재현의 전제).

## 데이터 모델

```
report_profile
  id (uuid) · name · description · report_type (DAILY | WEEKLY | MONTHLY | CUSTOM | ANY)
  current_version (int) · is_default (bool) · archived_at · created_by · created_at
  -- is_default: report_type별 최대 1개. ANY 기본 프로필은 반드시 1개 존재(최종 대체값)

report_profile_version            -- 불변(insert only)
  profile_id · version (int) · settings (json) · change_note · created_by · created_at
  PK(profile_id, version)

customer_report_config
  id · tenant_id · account_id (nullable: null이면 고객의 모든 계정)
  report_type (DAILY | WEEKLY | MONTHLY | CUSTOM | ANY)
  profile_id · profile_version_pin (nullable: null이면 항상 최신)
  overrides (json, settings와 같은 스키마의 부분집합)
  updated_by · updated_at
  -- 유일성: account_id가 null인 행과 아닌 행을 분리한 부분 유니크 인덱스 2개
  --   UNIQUE(tenant_id, report_type) WHERE account_id IS NULL
  --   UNIQUE(tenant_id, account_id, report_type) WHERE account_id IS NOT NULL
  --   (PostgreSQL 16 부분 유니크 인덱스, IF NOT EXISTS)

report_jobs (기존) + profile_id · profile_version · settings_snapshot (jsonb, 최종 유효 설정 전체, 모두 nullable)
```

settings JSON (프로필·overrides 공통 스키마):
```json
{
  "schema": 1,
  "layout":     { "sections": [{"key": "executive_summary", "enabled": true}] },
  "display_scope":      { "resource_categories": [], "monitoring_categories": [] },
  "collection_options": { "collect_wms": true, "collect_security_monitoring": true },
  "analysis":   { "enabled": true, "thresholds": { "cpu_warning_percent": 90 } },
  "branding":   { "logo": "tenant", "footer_note": "" }
}
```
- 섹션 순서 = `layout.sections` 배열 순서.
- **보존 정책**(`tenant_report_settings.settings.retention_policies`)과 **전달 설정**(T06 일정 `delivery`)은 프로필에 넣지 않습니다.
- `display_scope`는 표시 범위입니다(결정 D1). 이 값으로 수집 대상을 줄이지 않습니다.

### 유효 설정 해석
`resolve_settings(tenant_id, account_id, report_type, profile_override=None) -> (settings, provenance)` 를 한 곳에 구현합니다.

1. **프로필 선택** (위에서 처음 일치하는 것):
   `profile_override`(일정에 프로필이 지정된 경우) → `config(account, T)` → `config(tenant, T)` → `config(account, ANY)` → `config(tenant, ANY)` → 기본 프로필(T) → 기본 프로필(ANY).
   `T = CUSTOM`이고 CUSTOM용 설정이 하나도 없으면 같은 순서를 `DAILY`로 한 번 더 시도한 뒤 ANY로 갑니다(T04 동작 유지: 시간 범위 보고서는 일일 구성). 즉 CUSTOM → DAILY → ANY.
2. **버전**: 선택된 config의 `profile_version_pin`이 있으면 그 버전, 없으면 `current_version`.
3. **overrides 적용**: 해당 tenant의 config(account 행이 있으면 account 행, 없으면 tenant 행)의 overrides를 병합.
   `profile_override`가 있어도 고객 overrides는 적용합니다.
4. **병합 규칙**: overrides에 **키가 없으면 상속**, 키가 있으면 그 값으로 덮어씀(null·빈 문자열 포함), **배열은 통째로 교체**, 객체는 재귀 병합.
   "프로필 값으로 되돌리기" = overrides에서 해당 키를 **삭제**.
5. `provenance`: 각 최상위·2단계 키의 출처(`profile:{id}@v{n}` / `override:tenant` / `override:account`). UI 출처 배지에 사용.

생성 작업마다 `report_jobs.profile_id`, `profile_version`, `settings_snapshot`을 저장합니다(T07이 `report_version`으로 복사).

### 기존 설정 변환
T04에서 확장한 고객 설정 JSON(`tenant_report_settings.settings`, 유형별 키 포함)을 "고객 전용 프로필 + overrides 없음" 또는 "기본 프로필 + overrides"로 변환합니다.
변환은 원본 JSON을 지우지 않습니다(전진 수정·대조를 위해 보존, 정리는 별도 작업).
변환 규칙을 계획에 적고, **변환 전후 `resolve_settings` 결과가 모든 고객·계정·유형에서 동일**함을 검증하는 스크립트를 포함하세요.

## 화면

1. **사이드바** "자동화" 그룹에 **리포트 프로필** 메뉴 추가(T02에서 보류한 항목).
2. **`/msp/profiles` 목록** — 이름 / 유형 / 적용 고객 수 / 현재 버전 / 최근 수정. 행 `⋯`: 복제, 보관.
3. **프로필 편집** `/msp/profiles/{id}` — T04 출력 설정 UI 중 **구성·표시 범위·분석 기준·브랜딩** 4개 섹션을 재사용(보존 정책 제외).
   - 저장 시 새 버전 생성 + 변경 메모 입력. **변경 영향 미리보기**: "이 프로필을 최신으로 쓰는 고객 9곳의 다음 보고서부터 적용됩니다" + 고객 목록.
   - 버전 이력 탭: 버전별 diff(키 단위 전/후), "이 버전으로 되돌리기"(= 그 내용으로 새 버전 생성).
4. **고객 워크스페이스 › 출력 설정** — 유형별로 "적용 프로필" 선택(+ 버전 고정 옵션). 각 필드 옆 출처 배지(`프로필` / `고객 지정` / `계정 지정`)와 "프로필 값으로 되돌리기".
5. **일괄 적용** — 프로필 상세에서 "고객에 적용" → 고객 다중 선택 → 유형 선택 → 결과 요약.

## 완료 조건
- [ ] 마이그레이션이 추가형이고 빈 DB 2회 적용·기존 데이터 위 적용 성공, 전진 수정 계획 첨부(다운그레이드 스크립트 없음)
- [ ] 기존 설정 변환 후 `resolve_settings` 결과 전수 동일(검증 스크립트 출력 첨부)
- [ ] 프로필 저장마다 `report_profile_version` 1행 추가, 기존 버전 수정 불가(DB 제약 또는 애플리케이션 가드 + 테스트)
- [ ] 생성 작업에 `profile_id`·`profile_version`·`settings_snapshot` 저장
- [ ] 버전 고정한 고객은 프로필이 바뀌어도 고정 버전으로 생성
- [ ] tenant 행과 account 행 중복 방지(부분 유니크) 테스트
- [ ] 새 테이블 RLS·GRANT 테스트(고객 사용자 접근 불가, 고객·계정 불일치 FK 거부)
- [ ] 출처 배지와 "되돌리기"(키 삭제) 동작
- [ ] 권한: `MSP_ADMIN`만 프로필 편집, `MSP_OPERATOR`는 조회·적용만

## 검증
- `resolve_settings` 단위 테스트: 선택 순서 전 경로(CUSTOM→DAILY→ANY 대체 포함), 버전 고정, 키 없음=상속, null 덮어쓰기, 배열 교체, `profile_override`.
- 프로필 버전 고정/최신 추종 시나리오 통합 테스트.
