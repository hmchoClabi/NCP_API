\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.customer_deletion_tombstones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_code_hash char(64) NOT NULL,
    environment varchar(10) NOT NULL,
    report_count integer NOT NULL DEFAULT 0,
    archive_reference varchar(500),
    deleted_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    deleted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT customer_deletion_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT customer_deletion_report_count_check CHECK (report_count >= 0),
    CONSTRAINT customer_deletion_archive_check CHECK (
        report_count = 0 OR length(btrim(archive_reference)) > 0
    )
);

CREATE INDEX IF NOT EXISTS customer_deletion_tombstones_time_idx
ON control.customer_deletion_tombstones (deleted_at DESC);

ALTER TABLE audit.credential_access_logs
    ALTER COLUMN tenant_id DROP NOT NULL;
ALTER TABLE audit.credential_access_logs
    DROP CONSTRAINT IF EXISTS credential_access_logs_tenant_id_fkey;
ALTER TABLE audit.credential_access_logs
    ADD CONSTRAINT credential_access_logs_tenant_id_fkey
    FOREIGN KEY (tenant_id) REFERENCES control.tenants(id) ON DELETE SET NULL;

REVOKE ALL ON control.customer_deletion_tombstones FROM PUBLIC;
GRANT SELECT, INSERT ON control.customer_deletion_tombstones TO ncp_msp_app;

-- Anonymization may redact only personal fields. Keep all other audit fields
-- append-only for the application role.
GRANT UPDATE (email_attempted, source_ip, user_agent, failure_reason)
ON audit.authentication_logs TO ncp_msp_app;
GRANT UPDATE (source_ip, user_agent, details)
ON audit.access_logs TO ncp_msp_app;
GRANT UPDATE (changed_fields)
ON audit.data_change_logs TO ncp_msp_app;

GRANT SELECT ON control.schema_versions TO
    ncp_public_worker,
    ncp_gov_worker;

INSERT INTO control.schema_versions (version, description)
VALUES ('100', 'customer reactivation, anonymization and permanent deletion ledger')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
