\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS control.artifact_cleanup_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    storage_uri text NOT NULL,
    expected_sha256 char(64) NOT NULL,
    expected_byte_size bigint NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_error_code varchar(100),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT artifact_cleanup_outbox_size_check CHECK (
        expected_byte_size >= 0
    ),
    CONSTRAINT artifact_cleanup_outbox_checksum_check CHECK (
        expected_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT artifact_cleanup_outbox_attempt_check CHECK (
        attempt_count >= 0
    ),
    UNIQUE (operation_id, storage_uri)
);

CREATE INDEX IF NOT EXISTS artifact_cleanup_outbox_due_idx
ON control.artifact_cleanup_outbox (next_attempt_at, created_at);

ALTER TABLE control.artifact_cleanup_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.artifact_cleanup_outbox FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS artifact_cleanup_outbox_msp_access
ON control.artifact_cleanup_outbox;
CREATE POLICY artifact_cleanup_outbox_msp_access
ON control.artifact_cleanup_outbox
FOR ALL TO ncp_msp_app
USING (true)
WITH CHECK (true);

REVOKE ALL ON control.artifact_cleanup_outbox FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE
ON control.artifact_cleanup_outbox TO ncp_msp_app;

INSERT INTO control.schema_versions (version, description)
VALUES ('190', 'Durable and content-safe local artifact cleanup outbox')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;

COMMIT;
