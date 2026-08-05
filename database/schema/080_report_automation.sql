\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.account_report_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    cloud_account_id uuid NOT NULL,
    report_type varchar(20) NOT NULL,
    timezone varchar(64) NOT NULL DEFAULT 'Asia/Seoul',
    run_hour smallint NOT NULL DEFAULT 9,
    run_minute smallint NOT NULL DEFAULT 0,
    monthly_day smallint,
    enabled boolean NOT NULL DEFAULT true,
    next_run_at timestamptz NOT NULL,
    last_enqueued_at timestamptz,
    created_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT account_schedules_account_fk FOREIGN KEY (
        cloud_account_id, tenant_id
    ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT account_schedules_type_check CHECK (
        report_type IN ('DAILY', 'MONTHLY')
    ),
    CONSTRAINT account_schedules_clock_check CHECK (
        run_hour BETWEEN 0 AND 23 AND run_minute BETWEEN 0 AND 59
    ),
    CONSTRAINT account_schedules_monthly_day_check CHECK (
        (report_type = 'DAILY' AND monthly_day IS NULL)
        OR (report_type = 'MONTHLY' AND monthly_day BETWEEN 1 AND 28)
    ),
    UNIQUE (cloud_account_id, report_type)
);

CREATE INDEX IF NOT EXISTS account_schedules_due_idx
ON control.account_report_schedules (next_run_at)
WHERE enabled;

CREATE TABLE IF NOT EXISTS control.report_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    cloud_account_id uuid NOT NULL,
    environment varchar(10) NOT NULL,
    report_type varchar(20) NOT NULL,
    target_value varchar(20) NOT NULL,
    period_key varchar(40) NOT NULL,
    trigger_type varchar(20) NOT NULL,
    requested_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    schedule_id uuid REFERENCES control.account_report_schedules(id) ON DELETE SET NULL,
    status varchar(20) NOT NULL DEFAULT 'QUEUED',
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    locked_at timestamptz,
    locked_by varchar(200),
    started_at timestamptz,
    completed_at timestamptz,
    report_run_id uuid REFERENCES control.report_runs(id) ON DELETE SET NULL,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT report_jobs_account_fk FOREIGN KEY (
        cloud_account_id, tenant_id
    ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT report_jobs_environment_check CHECK (environment IN ('public', 'gov')),
    CONSTRAINT report_jobs_type_check CHECK (report_type IN ('DAILY', 'MONTHLY')),
    CONSTRAINT report_jobs_trigger_check CHECK (trigger_type IN ('MANUAL', 'SCHEDULED', 'RETRY')),
    CONSTRAINT report_jobs_status_check CHECK (
        status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')
    ),
    CONSTRAINT report_jobs_attempt_check CHECK (
        attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10
    ),
    UNIQUE (cloud_account_id, report_type, period_key)
);

CREATE INDEX IF NOT EXISTS report_jobs_claim_idx
ON control.report_jobs (environment, available_at, created_at)
WHERE status = 'QUEUED';

DROP TRIGGER IF EXISTS set_updated_at ON control.account_report_schedules;
CREATE TRIGGER set_updated_at BEFORE UPDATE ON control.account_report_schedules
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();
DROP TRIGGER IF EXISTS set_updated_at ON control.report_jobs;
CREATE TRIGGER set_updated_at BEFORE UPDATE ON control.report_jobs
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON
    control.account_report_schedules, control.report_jobs
TO ncp_msp_app;
GRANT SELECT, INSERT, UPDATE ON control.report_jobs TO
    ncp_public_worker, ncp_gov_worker;
GRANT DELETE ON control.report_artifacts, control.collection_errors TO
    ncp_public_worker, ncp_gov_worker;

ALTER TABLE control.account_report_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.account_report_schedules FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS schedules_msp_access ON control.account_report_schedules;
CREATE POLICY schedules_msp_access ON control.account_report_schedules
FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true);

ALTER TABLE control.report_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.report_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS report_jobs_msp_access ON control.report_jobs;
CREATE POLICY report_jobs_msp_access ON control.report_jobs
FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS report_jobs_public_worker_access ON control.report_jobs;
CREATE POLICY report_jobs_public_worker_access ON control.report_jobs
FOR ALL TO ncp_public_worker
USING (environment = 'public') WITH CHECK (environment = 'public');
DROP POLICY IF EXISTS report_jobs_gov_worker_access ON control.report_jobs;
CREATE POLICY report_jobs_gov_worker_access ON control.report_jobs
FOR ALL TO ncp_gov_worker
USING (environment = 'gov') WITH CHECK (environment = 'gov');

INSERT INTO control.schema_versions (version, description)
VALUES ('080', 'account report schedules and environment worker job queue')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
