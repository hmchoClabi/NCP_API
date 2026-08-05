\set ON_ERROR_STOP on

ALTER TABLE control.report_jobs
    ALTER COLUMN target_value TYPE varchar(80);

ALTER TABLE control.report_jobs
    ADD COLUMN IF NOT EXISTS period_start timestamptz,
    ADD COLUMN IF NOT EXISTS period_end timestamptz;

ALTER TABLE control.report_jobs
    DROP CONSTRAINT IF EXISTS report_jobs_type_check;
ALTER TABLE control.report_jobs
    ADD CONSTRAINT report_jobs_type_check CHECK (
        report_type IN ('DAILY', 'MONTHLY', 'CUSTOM')
    );

ALTER TABLE control.report_jobs
    DROP CONSTRAINT IF EXISTS report_jobs_period_check;
ALTER TABLE control.report_jobs
    ADD CONSTRAINT report_jobs_period_check CHECK (
        (report_type IN ('DAILY', 'MONTHLY')
            AND period_start IS NULL AND period_end IS NULL)
        OR (report_type = 'CUSTOM'
            AND period_start IS NOT NULL AND period_end IS NOT NULL
            AND period_start < period_end)
    );

ALTER TABLE control.report_jobs
    DROP CONSTRAINT IF EXISTS report_jobs_cloud_account_id_report_type_period_key_key;

CREATE UNIQUE INDEX IF NOT EXISTS report_jobs_active_period_uidx
ON control.report_jobs (cloud_account_id, report_type, period_key)
WHERE status IN ('QUEUED', 'RUNNING');

CREATE INDEX IF NOT EXISTS report_jobs_history_idx
ON control.report_jobs (tenant_id, created_at DESC);

-- Worker init containers only need to confirm that the expected schema exists.
-- Keep this narrower than granting access to the rest of the control schema.
GRANT SELECT ON control.schema_versions TO
    ncp_public_worker,
    ncp_gov_worker;

DO $$
DECLARE
    data_schema text;
BEGIN
    FOREACH data_schema IN ARRAY ARRAY['public_data', 'gov_data']
    LOOP
        EXECUTE format(
            'DROP INDEX IF EXISTS %I.insight_events_source_uidx',
            data_schema
        );
        EXECUTE format(
            'CREATE UNIQUE INDEX insight_events_source_uidx '
            'ON %I.insight_events '
            '(report_run_id, source_event_id, occurred_at) '
            'WHERE source_event_id IS NOT NULL',
            data_schema
        );
        EXECUTE format(
            'DROP INDEX IF EXISTS %I.activity_events_source_uidx',
            data_schema
        );
        EXECUTE format(
            'CREATE UNIQUE INDEX activity_events_source_uidx '
            'ON %I.activity_events '
            '(report_run_id, source_event_id, occurred_at) '
            'WHERE source_event_id IS NOT NULL',
            data_schema
        );
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('090', 'custom time ranges and immutable report execution history')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
