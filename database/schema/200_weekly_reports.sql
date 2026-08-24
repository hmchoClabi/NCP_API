\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE control.account_report_schedules
    ADD COLUMN IF NOT EXISTS weekly_day smallint;

ALTER TABLE control.account_report_schedules
    DROP CONSTRAINT IF EXISTS account_schedules_type_check;
ALTER TABLE control.account_report_schedules
    ADD CONSTRAINT account_schedules_type_check CHECK (
        report_type IN ('DAILY', 'WEEKLY', 'MONTHLY')
    );

ALTER TABLE control.account_report_schedules
    DROP CONSTRAINT IF EXISTS account_schedules_monthly_day_check;
ALTER TABLE control.account_report_schedules
    DROP CONSTRAINT IF EXISTS account_schedules_period_day_check;
ALTER TABLE control.account_report_schedules
    ADD CONSTRAINT account_schedules_period_day_check CHECK (
        (report_type = 'DAILY'
            AND weekly_day IS NULL AND monthly_day IS NULL)
        OR (report_type = 'WEEKLY'
            AND weekly_day BETWEEN 1 AND 7 AND monthly_day IS NULL)
        OR (report_type = 'MONTHLY'
            AND weekly_day IS NULL AND monthly_day BETWEEN 1 AND 28)
    );

ALTER TABLE control.report_jobs
    DROP CONSTRAINT IF EXISTS report_jobs_type_check;
ALTER TABLE control.report_jobs
    ADD CONSTRAINT report_jobs_type_check CHECK (
        report_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'CUSTOM')
    );

ALTER TABLE control.report_jobs
    DROP CONSTRAINT IF EXISTS report_jobs_period_check;
ALTER TABLE control.report_jobs
    ADD CONSTRAINT report_jobs_period_check CHECK (
        (report_type IN ('DAILY', 'WEEKLY', 'MONTHLY')
            AND period_start IS NULL AND period_end IS NULL)
        OR (report_type = 'CUSTOM'
            AND period_start IS NOT NULL AND period_end IS NOT NULL
            AND period_start < period_end)
    );

ALTER TABLE control.report_runs
    DROP CONSTRAINT IF EXISTS report_runs_type_check;
ALTER TABLE control.report_runs
    ADD CONSTRAINT report_runs_type_check CHECK (
        report_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'CUSTOM')
    );

ALTER TABLE control.report_schedules
    DROP CONSTRAINT IF EXISTS report_schedules_type_check;
ALTER TABLE control.report_schedules
    ADD CONSTRAINT report_schedules_type_check CHECK (
        report_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'CUSTOM')
    );

INSERT INTO control.schema_versions (version, description)
VALUES ('200', 'weekly report periods and account schedules')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
