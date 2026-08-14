# 운영 분석 보고서 적용 및 원복

## 원복 기준점

- 변경 전 커밋: `16cd770186449ab927dabd5e1a6960fe5212dfcd`
- Git 태그: `rollback/pre-operational-report-20260813`

태그는 사용자의 기존 변경을 덮어쓰지 않고 변경 전 코드를 다시 빌드할 수 있는
기준점이다. 현재 작업 트리를 강제로 되돌리는 `git reset --hard`는 사용하지 않는다.

## 가장 빠른 기능 원복

운영 분석 결과가 만족스럽지 않으면 코드나 DB를 되돌리지 않고 기능 플래그만
비활성화한다.

```powershell
helm upgrade ncp-report .\deploy\helm\ncp-report `
  --namespace ncp-report `
  --reuse-values `
  --set operationalAnalysis.enabled=false `
  --wait --wait-for-jobs --timeout 15m
```

이 설정은 신규 보고서의 결정론적 분석, WMS 및 Security Monitoring 선택 수집을
중단한다. 이미 저장된 보고서와 조치 이력은 삭제하지 않는다. 다시 활성화할 때는
같은 값을 `true`로 지정한다.

특정 고객만 원복하려면 MSP 고객 상세의 **결정론적 운영 분석 사용**을 해제한다.

## 코드 버전 원복

변경 전 버전을 별도 브랜치에서 재빌드하려면 다음처럼 태그에서 새 브랜치를 만든다.

```powershell
git switch -c rollback-operational-report rollback/pre-operational-report-20260813
```

현재 브랜치의 미커밋 변경을 먼저 보관하거나 커밋한 후 실행한다. 기존 브랜치를
강제로 덮어쓰지 않는다.

## DB 마이그레이션 원칙

`180_operational_analysis.sql`은 기존 테이블의 구버전 쓰기 키를 유지하는
forward-compatible 마이그레이션이다. `event_cases`에 분석 필드를 추가하고
`daily_account_facts`, `policy_exceptions` 테이블을 만든다. 기존
`daily_customer_facts`의 `(tenant_id, fact_date)` 키와 구버전 사건 upsert 키는
보존되므로 기능 또는 코드 원복 시 DB를 내릴 필요가 없다.

DB 객체 삭제는 조치 이력과 예외 승인 기록을 잃을 수 있으므로 자동 원복 SQL을
제공하지 않는다. 완전 제거가 필요하면 먼저 `event_cases`와 `policy_exceptions`를
백업하고 보존 규정을 확인한 뒤 별도 변경 작업으로 수행한다.

## 배포 전 확인

1. PostgreSQL 백업을 생성하고 복원 목록 검증이 성공했는지 확인한다.
2. 마이그레이션 Job이 스키마 버전 `180`을 기록했는지 확인한다.
3. 한 개 테스트 고객에서 분석을 활성화하고 데이터 수집 상태의 0건/실패 구분을
   확인한다.
4. WMS와 Security Monitoring은 권한을 확인한 고객만 개별 활성화한다.
5. 이상이 있으면 전역 기능 플래그를 끄고 기존 보고서 생성 동작을 확인한다.

## 의도적으로 확정하지 않는 항목

- Cloud Insight 이벤트의 발생~종료 시간은 MTTA/MTTR로 표시하지 않는다.
- API가 제공하지 않은 장애 원인, 승인 여부, 백업 성공 여부, 공개 포트는 추정하지
  않는다.
- 동일 금액 기준·신뢰도·할인·VAT 범위이면서 서로 다른 대상 기간인 비용만
  비교한다.
- WMS 또는 Security Monitoring이 비활성화되거나 실패하면 0건이나 정상으로
  표시하지 않는다.
- `수집·검사 범위 내 정상`은 선택되어 성공한 데이터 원본과 구현된 규칙의
  판정이다. 비활성화·미지원·수집 실패한 상품까지 전체 정상이라는 뜻이 아니다.
- Security Monitoring 자동 수집은 현재 VPC API 범위다. Classic 보안 이벤트는
  수집하지 않으며 정상으로 간주하지 않는다.
- Activity Tracer의 실패는 변경 작업으로 단정하지 않고 실패한 활동으로
  표시한다. 조회와 변경의 구분은 공급자 액션 원문을 확인한다.
- 공개 포트, 의심 로그인, 인증키 미사용 기간, 복구 테스트 성공 여부는 해당
  원본 수집·정책 판정이 구현되기 전까지 보고서가 추정하지 않는다.
- 최근 7일·30일 동적 이상 탐지, SLA/SLO 달성률, MTTA/MTTR, 예상 절감액은
  이번 단계에서 제공하지 않는다. 고객별 고정 임계치와 동일 기준 이전 보고서
  비교만 사용한다.

## 배포 전 DB 사전 점검

`180`은 기존 `ANALYSIS` 사건에 계정·환경 불변식을 추가한다. 실제 DB에 적용하기
전에 다음 쿼리 결과가 0건인지 확인한다. 결과가 있으면 자동으로 추정해 넘기지
말고 해당 행의 보고서·계정 관계를 복구한 뒤 마이그레이션한다.

```sql
SELECT event_case.id
FROM control.event_cases event_case
LEFT JOIN control.report_runs report_run
  ON report_run.id = event_case.latest_report_run_id
 AND report_run.tenant_id = event_case.tenant_id
WHERE event_case.source_type = 'ANALYSIS'
  AND (
    event_case.cloud_account_id IS NULL
    OR report_run.id IS NULL
  );

SELECT event_case.id
FROM control.event_cases event_case
JOIN control.tenants tenant ON tenant.id = event_case.tenant_id
WHERE event_case.environment <> tenant.environment;
```
