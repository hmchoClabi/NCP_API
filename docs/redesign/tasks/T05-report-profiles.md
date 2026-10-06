# T05 — 리포트 프로필 (재사용 가능한 보고서 구성 템플릿 + 버전 관리)

> 선행: T04. 스키마 변경 폭이 큰 작업입니다. 계획 단계에서 스키마와 기존 설정 변환 규칙을 먼저 승인받으세요.
> 보고서 유형 값은 `00-context.md` 11절 열거형을 따릅니다.

## 목표
고객이 늘어날수록 고객마다 섹션·범주·임계치를 하나씩 맞추는 방식은 유지가 어렵습니다.
**프로필**(예: "공공 표준 일일", "민간 경영진 월간")을 만들어 여러 고객·계정에 적용하고, 고객별로 필요한 항목만 덮어쓰게 합니다.
프로필과 고객 설정은 **버전 관리**되어, 보고서가 어떤 설정으로 만들어졌는지 언제든 복원할 수 있어야 합니다(T07 재현의 전제).

## 데이터 모델

```
report_profile
  id (uuid) · name · description · report_type (DAILY | WEEKLY | MONTHLY | RANGE | ANY)
  current_version (int) · is_default (bool) · archived_at · created_by · created_at
  -- is_default: report_type별 최대 1개. ANY 기본 프로필은 반드시 1개 존재(최종 대체값)

report_profile_version            -- 불변(insert only)
  profile_id · version (int) · settings (json) · change_note · created_by · created_at
  PK(profile_id, version)

customer_report_config
  id · tenant_id · account_id (nullable: null이면 고객의 모든 계정)
  report_type (DAILY | WEEKLY | MONTHLY | RANGE | ANY)
  profile_id · profile_version_pin (nullable: null이면 항상 최신)
  overrides (json, settings와 같은 스키마의 부분집합)
  updated_by · updated_at
  -- 유일성: account_id가 null인 행과 아닌 행을 분리한 부분 유니크 인덱스 2개
  --   UNIQUE(tenant_id, report_type) WHERE account_id IS NULL
  --   UNIQUE(tenant_id, account_id, report_type) WHERE account_id IS NOT NULL
  --   (DB가 부분 인덱스를 지원하지 않으면 계획에 대체안 제시)

report_job (기존) + profile_id · profile_version · settings_snapshot (json, 최종 유효 설정 전체)
```

settings JSON (프로필·overrides 공통 스키마):
```json
{
  "schema": 1,
  "layout":     { "sections": [{"key": "executive_summary", "enabled": true}] },
  "collection": { "resource_categories": [], "monitoring_categories": [], "collect_wms": true, "collect_security_monitoring": true },
  "analysis":   { "enabled": true, "thresholds": { "cpu_warning_percent": 90 } },
  "branding":   { "logo": "tenant", "footer_note": "" }
}
```
- 섹션 순서 = `layout.sections` 배열 순서.
- **보존 정책**(T04 `customer_retention_policy`)과 **전달 설정**(T06 일정 `delivery`)은 프로필에 넣지 않습니다.

### 유효 설정 해석
`resolve_settings(tenant_id, account_id, report_type, profile_override=None) -> (settings, provenance)` 를 한 곳에 구현합니다.

1. **프로필 선택** (위에서 처음 일치하는 것):
   `profile_override`(일정에 프로필이 지정된 경우) → `config(account, T)` → `config(tenant, T)` → `config(account, ANY)` → `config(tenant, ANY)` → 기본 프로필(T) → 기본 프로필(ANY).
   `T = RANGE`이고 RANGE용 설정이 하나도 없으면 같은 순서를 `DAILY`로 한 번 더 시도한 뒤 ANY로 갑니다(T04 동작 유지).
2. **버전**: 선택된 config의 `profile_version_pin`이 있으면 그 버전, 없으면 `current_version`.
3. **overrides 적용**: 해당 tenant의 config(account 행이 있으면 account 행, 없으면 tenant 행)의 overrides를 병합.
   `profile_override`가 있어도 고객 overrides는 적용합니다.
4. **병합 규칙**: overrides에 **키가 없으면 상속**, 키가 있으면 그 값으로 덮어씀(null·빈 문자열 포함), **배열은 통째로 교체**, 객체는 재귀 병합.
   "프로필 값으로 되돌리기" = overrides에서 해당 키를 **삭제**.
5. `provenance`: 각 최상위·2단계 키의 출처(`profile:{id}@v{n}` / `override:tenant` / `override:account`). UI 출처 배지에 사용.

생성 작업마다 `report_job.profile_id`, `profile_version`, `settings_snapshot`을 저장합니다(T07이 `report_version`으로 복사).

### 기존 설정 변환
T04에서 만든 고객별 유형 설정(`report_type`별 행)을 "고객 전용 프로필 + overrides 없음" 또는 "기본 프로필 + overrides"로 변환합니다.
변환 규칙을 계획에 적고, **변환 전후 `resolve_settings` 결과가 모든 고객·계정·유형에서 동일**함을 검증하는 스크립트를 포함하세요.

## 화면

1. **사이드바** "자동화" 그룹에 **리포트 프로필** 메뉴 추가(T02에서 보류한 항목).
2. **`/msp/profiles` 목록** — 이름 / 유형 / 적용 고객 수 / 현재 버전 / 최근 수정. 행 `⋯`: 복제, 보관.
3. **프로필 편집** `/msp/profiles/{id}` — T04 출력 설정 UI 중 **구성·수집 범위·분석 기준·브랜딩** 4개 섹션을 재사용(보존 정책 제외).
   - 저장 시 새 버전 생성 + 변경 메모 입력. **변경 영향 미리보기**: "이 프로필을 최신으로 쓰는 고객 9곳의 다음 보고서부터 적용됩니다" + 고객 목록.
   - 버전 이력 탭: 버전별 diff(키 단위 전/후), "이 버전으로 되돌리기"(= 그 내용으로 새 버전 생성).
4. **고객 워크스페이스 › 출력 설정** — 유형별로 "적용 프로필" 선택(+ 버전 고정 옵션). 각 필드 옆 출처 배지(`프로필` / `고객 지정` / `계정 지정`)와 "프로필 값으로 되돌리기".
5. **일괄 적용** — 프로필 상세에서 "고객에 적용" → 고객 다중 선택 → 유형 선택 → 결과 요약.

## 완료 조건
- [ ] 마이그레이션 업/다운 동작, 기존 설정 변환 후 `resolve_settings` 결과 전수 동일(검증 스크립트 출력 첨부)
- [ ] 프로필 저장마다 `report_profile_version` 1행 추가, 기존 버전 수정 불가(DB 제약 또는 애플리케이션 가드 + 테스트)
- [ ] 생성 작업에 `profile_id`·`profile_version`·`settings_snapshot` 저장
- [ ] 버전 고정한 고객은 프로필이 바뀌어도 고정 버전으로 생성
- [ ] tenant 행과 account 행 중복 방지(부분 유니크) 테스트
- [ ] 출처 배지와 "되돌리기"(키 삭제) 동작
- [ ] 권한: MSP 관리자만 프로필 편집, 운영자는 조회·적용만(실제 역할 체계는 T00 결과에 맞춤)

## 검증
- `resolve_settings` 단위 테스트: 선택 순서 전 경로(RANGE→DAILY 대체 포함), 버전 고정, 키 없음=상속, null 덮어쓰기, 배열 교체, `profile_override`.
- 프로필 버전 고정/최신 추종 시나리오 통합 테스트.
