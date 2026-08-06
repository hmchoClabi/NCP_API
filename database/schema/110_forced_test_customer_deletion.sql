\set ON_ERROR_STOP on

ALTER TABLE control.customer_deletion_tombstones
    ADD COLUMN IF NOT EXISTS forced boolean NOT NULL DEFAULT false;

ALTER TABLE control.customer_deletion_tombstones
    DROP CONSTRAINT IF EXISTS customer_deletion_archive_check;
ALTER TABLE control.customer_deletion_tombstones
    ADD CONSTRAINT customer_deletion_archive_check CHECK (
        report_count = 0
        OR forced
        OR COALESCE(length(btrim(archive_reference)), 0) > 0
    );

INSERT INTO control.schema_versions (version, description)
VALUES ('110', 'audited forced deletion for test customers with reports')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
