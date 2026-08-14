\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE control.event_cases
    DROP CONSTRAINT IF EXISTS event_cases_source_check;
ALTER TABLE control.event_cases
    ADD CONSTRAINT event_cases_source_check CHECK (
        source_type IN ('INSIGHT', 'ACTIVITY', 'COLLECTION', 'ANALYSIS')
    );

ALTER TABLE control.event_cases
    ADD COLUMN IF NOT EXISTS latest_report_run_id uuid,
    ADD COLUMN IF NOT EXISTS cloud_account_id uuid,
    ADD COLUMN IF NOT EXISTS report_type varchar(20),
    ADD COLUMN IF NOT EXISTS rule_id varchar(120),
    ADD COLUMN IF NOT EXISTS resource_id varchar(500),
    ADD COLUMN IF NOT EXISTS category varchar(50),
    ADD COLUMN IF NOT EXISTS evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS impact text,
    ADD COLUMN IF NOT EXISTS recommendation text,
    ADD COLUMN IF NOT EXISTS priority varchar(20),
    ADD COLUMN IF NOT EXISTS due_at timestamptz,
    ADD COLUMN IF NOT EXISTS first_detected_at timestamptz
        NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN IF NOT EXISTS last_detected_at timestamptz
        NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN IF NOT EXISTS occurrence_count integer NOT NULL DEFAULT 1;

-- 180의 초기 개발본이 단일 컬럼 FK를 만든 환경에서도 재실행할 수 있게
-- 기존 제약을 먼저 제거하고 tenant까지 포함한 복합 FK로 일관되게 교체한다.
ALTER TABLE control.event_cases
    DROP CONSTRAINT IF EXISTS event_cases_latest_report_run_id_fkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.event_cases'::regclass
          AND conname = 'event_cases_latest_run_tenant_fk'
    ) THEN
        ALTER TABLE control.event_cases
        ADD CONSTRAINT event_cases_latest_run_tenant_fk FOREIGN KEY (
            latest_report_run_id, tenant_id
        ) REFERENCES control.report_runs(id, tenant_id)
          ON DELETE SET NULL (latest_report_run_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.event_cases'::regclass
          AND conname = 'event_cases_tenant_environment_fk'
    ) THEN
        ALTER TABLE control.event_cases
        ADD CONSTRAINT event_cases_tenant_environment_fk FOREIGN KEY (
            tenant_id, environment
        ) REFERENCES control.tenants(id, environment) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.event_cases'::regclass
          AND conname = 'event_cases_cloud_account_tenant_fk'
    ) THEN
        ALTER TABLE control.event_cases
        ADD CONSTRAINT event_cases_cloud_account_tenant_fk FOREIGN KEY (
            cloud_account_id, tenant_id
        ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE;
    END IF;
END;
$$;

UPDATE control.event_cases event_case
SET cloud_account_id = report_run.cloud_account_id,
    report_type = report_run.report_type
FROM control.report_runs report_run
WHERE event_case.source_type = 'ANALYSIS'
  AND (
      event_case.cloud_account_id IS NULL
      OR event_case.report_type IS NULL
  )
  AND event_case.latest_report_run_id = report_run.id
  AND event_case.tenant_id = report_run.tenant_id;

ALTER TABLE control.event_cases
    DROP CONSTRAINT IF EXISTS event_cases_evidence_check,
    DROP CONSTRAINT IF EXISTS event_cases_priority_check,
    DROP CONSTRAINT IF EXISTS event_cases_occurrence_count_check,
    DROP CONSTRAINT IF EXISTS event_cases_analysis_account_check,
    DROP CONSTRAINT IF EXISTS event_cases_status_check;
ALTER TABLE control.event_cases
    ADD CONSTRAINT event_cases_evidence_check CHECK (
        jsonb_typeof(evidence) = 'array'
    ),
    ADD CONSTRAINT event_cases_priority_check CHECK (
        priority IS NULL OR priority IN ('P1', 'P2', 'P3', 'P4')
    ),
    ADD CONSTRAINT event_cases_occurrence_count_check CHECK (
        occurrence_count > 0
    ),
    ADD CONSTRAINT event_cases_analysis_account_check CHECK (
        source_type <> 'ANALYSIS'
        OR (cloud_account_id IS NOT NULL AND report_type IS NOT NULL)
    ),
    ADD CONSTRAINT event_cases_status_check CHECK (
        status IN (
            'NEW', 'ACKNOWLEDGED', 'IN_PROGRESS',
            'RESOLVED', 'IGNORED', 'NOT_DETECTED'
        )
    );

-- NOT VALID을 사용하지 않고 기존 행까지 즉시 검증한다. 계정을 복원할 수 없는
-- ANALYSIS 행이 있으면 격리 경계를 약화시키지 않고 마이그레이션을 실패시킨다.
ALTER TABLE control.event_cases
    VALIDATE CONSTRAINT event_cases_analysis_account_check;

CREATE INDEX IF NOT EXISTS event_cases_analysis_account_idx
ON control.event_cases (
    tenant_id, cloud_account_id, source_type, status, priority,
    last_detected_at DESC
)
WHERE source_type = 'ANALYSIS';

-- 기존 전역 unique 제약은 구버전 코드 원복 시 ON CONFLICT 대상으로
-- 사용되므로 유지한다. 분석 사건의 source_event_id에는 계정 ID가 포함된다.

DROP INDEX IF EXISTS control.event_cases_analysis_identity_uidx;
CREATE UNIQUE INDEX event_cases_analysis_identity_uidx
ON control.event_cases (
    tenant_id, cloud_account_id, report_type, source_type, source_event_id
)
WHERE source_type = 'ANALYSIS';

CREATE INDEX IF NOT EXISTS event_cases_analysis_idx
ON control.event_cases (
    tenant_id, source_type, status, priority, last_detected_at DESC
);

CREATE INDEX IF NOT EXISTS event_cases_latest_report_run_idx
ON control.event_cases (latest_report_run_id);

-- 기존 daily_customer_facts의 (tenant_id, fact_date) 계약은 구버전 코드
-- 원복을 위해 유지한다. 새 계정별 사실은 별도 테이블에 저장하고 기존
-- 테이블에는 고객 단위 합계를 계속 기록한다.
CREATE TABLE IF NOT EXISTS control.daily_account_facts (
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    cloud_account_id uuid NOT NULL,
    fact_date date NOT NULL,
    environment varchar(10) NOT NULL,
    latest_report_run_id uuid,
    collection_status varchar(30),
    server_count integer NOT NULL DEFAULT 0,
    critical_count integer NOT NULL DEFAULT 0,
    warning_count integer NOT NULL DEFAULT 0,
    info_count integer NOT NULL DEFAULT 0,
    activity_failure_count integer NOT NULL DEFAULT 0,
    collection_error_count integer NOT NULL DEFAULT 0,
    estimated_cost numeric(20, 4),
    confirmed_cost numeric(20, 4),
    cost_confidence varchar(30),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, cloud_account_id, fact_date),
    CONSTRAINT daily_account_facts_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT daily_account_facts_tenant_environment_fk FOREIGN KEY (
        tenant_id, environment
    ) REFERENCES control.tenants(id, environment) ON DELETE CASCADE,
    CONSTRAINT daily_account_facts_cloud_account_tenant_fk FOREIGN KEY (
        cloud_account_id, tenant_id
    ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT daily_account_facts_latest_run_tenant_fk FOREIGN KEY (
        latest_report_run_id, tenant_id
    ) REFERENCES control.report_runs(id, tenant_id)
      ON DELETE SET NULL (latest_report_run_id),
    CONSTRAINT daily_account_facts_counts_check CHECK (
        server_count >= 0
        AND critical_count >= 0
        AND warning_count >= 0
        AND info_count >= 0
        AND activity_failure_count >= 0
        AND collection_error_count >= 0
    ),
    CONSTRAINT daily_account_facts_cost_confidence_check CHECK (
        cost_confidence IS NULL
        OR cost_confidence IN (
            'CONFIRMED', 'VERIFIED_ESTIMATE', 'PARTIAL', 'UNAVAILABLE'
        )
    )
);

-- 180 적용 전 고객/일자 사실을 연결된 최신 보고서의 계정 사실로 보존한다.
-- 과거 테이블이 마지막 쓰기 한 계정만 담았던 경우 그 이상은 추정하지 않는다.
INSERT INTO control.daily_account_facts (
    tenant_id, cloud_account_id, fact_date, environment,
    latest_report_run_id, collection_status, server_count,
    critical_count, warning_count, info_count, activity_failure_count,
    collection_error_count, estimated_cost, confirmed_cost,
    cost_confidence, updated_at
)
SELECT
    fact.tenant_id,
    report_run.cloud_account_id,
    fact.fact_date,
    fact.environment,
    fact.latest_report_run_id,
    fact.collection_status,
    fact.server_count,
    fact.critical_count,
    fact.warning_count,
    fact.info_count,
    fact.activity_failure_count,
    fact.collection_error_count,
    fact.estimated_cost,
    fact.confirmed_cost,
    fact.cost_confidence,
    fact.updated_at
FROM control.daily_customer_facts fact
JOIN control.report_runs report_run
  ON report_run.id = fact.latest_report_run_id
 AND report_run.tenant_id = fact.tenant_id
WHERE report_run.cloud_account_id IS NOT NULL
ON CONFLICT (tenant_id, cloud_account_id, fact_date) DO NOTHING;

CREATE INDEX IF NOT EXISTS daily_account_facts_date_event_idx
ON control.daily_account_facts (
    fact_date DESC, critical_count DESC, warning_count DESC
);

CREATE INDEX IF NOT EXISTS daily_account_facts_latest_run_idx
ON control.daily_account_facts (latest_report_run_id);

ALTER TABLE control.daily_account_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.daily_account_facts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS daily_account_facts_customer_access
ON control.daily_account_facts;
CREATE POLICY daily_account_facts_customer_access
ON control.daily_account_facts FOR SELECT TO ncp_control_app
USING (tenant_id = control.current_tenant_id());

DROP POLICY IF EXISTS daily_account_facts_msp_access
ON control.daily_account_facts;
CREATE POLICY daily_account_facts_msp_access
ON control.daily_account_facts FOR ALL TO ncp_msp_app
USING (
    tenant_id = control.current_tenant_id()
    AND environment = NULLIF(
        current_setting('app.environment_scope', true), ''
    )
)
WITH CHECK (
    tenant_id = control.current_tenant_id()
    AND environment = NULLIF(
        current_setting('app.environment_scope', true), ''
    )
);

DROP POLICY IF EXISTS daily_account_facts_public_worker_access
ON control.daily_account_facts;
CREATE POLICY daily_account_facts_public_worker_access
ON control.daily_account_facts FOR ALL TO ncp_public_worker
USING (
    tenant_id = control.current_tenant_id() AND environment = 'public'
)
WITH CHECK (
    tenant_id = control.current_tenant_id() AND environment = 'public'
);

DROP POLICY IF EXISTS daily_account_facts_gov_worker_access
ON control.daily_account_facts;
CREATE POLICY daily_account_facts_gov_worker_access
ON control.daily_account_facts FOR ALL TO ncp_gov_worker
USING (
    tenant_id = control.current_tenant_id() AND environment = 'gov'
)
WITH CHECK (
    tenant_id = control.current_tenant_id() AND environment = 'gov'
);

GRANT SELECT ON control.daily_account_facts TO ncp_control_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON control.daily_account_facts TO
    ncp_msp_app,
    ncp_public_worker,
    ncp_gov_worker;

DROP POLICY IF EXISTS tenant_msp_access ON control.event_cases;
CREATE POLICY tenant_msp_access
ON control.event_cases FOR ALL TO ncp_msp_app
USING (tenant_id = control.current_tenant_id())
WITH CHECK (tenant_id = control.current_tenant_id());

CREATE TABLE IF NOT EXISTS control.policy_exceptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    cloud_account_id uuid,
    environment varchar(10) NOT NULL,
    rule_id varchar(120) NOT NULL,
    resource_id varchar(500),
    reason text NOT NULL,
    expires_at timestamptz NOT NULL,
    active boolean NOT NULL DEFAULT true,
    approved_by uuid NOT NULL REFERENCES control.users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT policy_exceptions_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT policy_exceptions_reason_check CHECK (
        length(btrim(reason)) BETWEEN 1 AND 2000
    ),
    CONSTRAINT policy_exceptions_expiry_check CHECK (
        expires_at > created_at
    ),
    CONSTRAINT policy_exceptions_tenant_environment_fk FOREIGN KEY (
        tenant_id, environment
    ) REFERENCES control.tenants(id, environment) ON DELETE CASCADE
);

ALTER TABLE control.policy_exceptions
    ADD COLUMN IF NOT EXISTS cloud_account_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.policy_exceptions'::regclass
          AND conname = 'policy_exceptions_cloud_account_tenant_fk'
    ) THEN
        ALTER TABLE control.policy_exceptions
        ADD CONSTRAINT policy_exceptions_cloud_account_tenant_fk FOREIGN KEY (
            cloud_account_id, tenant_id
        ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS policy_exceptions_active_account_idx
ON control.policy_exceptions (
    tenant_id, cloud_account_id, rule_id, resource_id, expires_at
)
WHERE active;

CREATE INDEX IF NOT EXISTS policy_exceptions_cloud_account_idx
ON control.policy_exceptions (cloud_account_id)
WHERE cloud_account_id IS NOT NULL;

DROP TRIGGER IF EXISTS set_updated_at ON control.policy_exceptions;
CREATE TRIGGER set_updated_at
BEFORE UPDATE ON control.policy_exceptions
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();

ALTER TABLE control.policy_exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.policy_exceptions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS policy_exceptions_customer_access
ON control.policy_exceptions;
CREATE POLICY policy_exceptions_customer_access
ON control.policy_exceptions FOR SELECT TO ncp_control_app
USING (tenant_id = control.current_tenant_id())
;

DROP POLICY IF EXISTS policy_exceptions_msp_access
ON control.policy_exceptions;
CREATE POLICY policy_exceptions_msp_access
ON control.policy_exceptions FOR ALL TO ncp_msp_app
USING (
    tenant_id = control.current_tenant_id()
    AND environment = NULLIF(
        current_setting('app.environment_scope', true), ''
    )
)
WITH CHECK (
    tenant_id = control.current_tenant_id()
    AND environment = NULLIF(
        current_setting('app.environment_scope', true), ''
    )
);

DROP POLICY IF EXISTS policy_exceptions_public_worker_access
ON control.policy_exceptions;
CREATE POLICY policy_exceptions_public_worker_access
ON control.policy_exceptions FOR SELECT TO ncp_public_worker
USING (
    tenant_id = control.current_tenant_id() AND environment = 'public'
);

DROP POLICY IF EXISTS policy_exceptions_gov_worker_access
ON control.policy_exceptions;
CREATE POLICY policy_exceptions_gov_worker_access
ON control.policy_exceptions FOR SELECT TO ncp_gov_worker
USING (
    tenant_id = control.current_tenant_id() AND environment = 'gov'
);

GRANT SELECT ON control.policy_exceptions TO ncp_control_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON control.policy_exceptions TO
    ncp_msp_app;
GRANT SELECT ON control.policy_exceptions TO
    ncp_public_worker,
    ncp_gov_worker;

INSERT INTO control.schema_versions (version, description)
VALUES ('180', 'Deterministic operational findings, action cases and policy exceptions')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
