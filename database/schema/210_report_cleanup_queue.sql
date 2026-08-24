\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE control.report_runs
    ADD COLUMN IF NOT EXISTS cleanup_requested_at timestamptz,
    ADD COLUMN IF NOT EXISTS cleanup_requested_by uuid
        REFERENCES control.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cleanup_reason varchar(30),
    ADD COLUMN IF NOT EXISTS cleanup_attempt_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cleanup_next_attempt_at timestamptz,
    ADD COLUMN IF NOT EXISTS cleanup_last_error_code varchar(100);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'report_runs_cleanup_reason_check'
          AND conrelid = 'control.report_runs'::regclass
    ) THEN
        ALTER TABLE control.report_runs
        ADD CONSTRAINT report_runs_cleanup_reason_check CHECK (
            cleanup_reason IS NULL
            OR cleanup_reason IN ('MANUAL', 'RETENTION_POLICY')
        );
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'report_runs_cleanup_attempt_check'
          AND conrelid = 'control.report_runs'::regclass
    ) THEN
        ALTER TABLE control.report_runs
        ADD CONSTRAINT report_runs_cleanup_attempt_check CHECK (
            cleanup_attempt_count >= 0
        );
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'report_runs_cleanup_state_check'
          AND conrelid = 'control.report_runs'::regclass
    ) THEN
        ALTER TABLE control.report_runs
        ADD CONSTRAINT report_runs_cleanup_state_check CHECK (
            cleanup_requested_at IS NULL
            OR (
                cleanup_reason IS NOT NULL
                AND cleanup_next_attempt_at IS NOT NULL
            )
        );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS report_runs_cleanup_due_idx
ON control.report_runs (
    cleanup_next_attempt_at, cleanup_requested_at, id
)
WHERE cleanup_requested_at IS NOT NULL;

INSERT INTO control.schema_versions (version, description)
VALUES ('210', 'Durable report cleanup requests and retention processing')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;

COMMIT;
