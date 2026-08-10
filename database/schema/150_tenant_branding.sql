\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS control.tenant_branding (
    tenant_id uuid PRIMARY KEY REFERENCES control.tenants(id) ON DELETE CASCADE,
    logo_content bytea NOT NULL,
    logo_content_type varchar(20) NOT NULL,
    logo_width integer NOT NULL,
    logo_height integer NOT NULL,
    logo_sha256 char(64) NOT NULL,
    updated_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT tenant_branding_logo_size_check CHECK (
        octet_length(logo_content) BETWEEN 1 AND 524288
    ),
    CONSTRAINT tenant_branding_logo_content_type_check CHECK (
        logo_content_type IN ('image/png', 'image/jpeg', 'image/webp')
    ),
    CONSTRAINT tenant_branding_logo_dimensions_check CHECK (
        logo_width BETWEEN 1 AND 4096
        AND logo_height BETWEEN 1 AND 4096
        AND logo_width::bigint * logo_height::bigint <= 8000000
    ),
    CONSTRAINT tenant_branding_logo_sha256_check CHECK (
        logo_sha256 ~ '^[0-9a-f]{64}$'
    )
);

DROP TRIGGER IF EXISTS set_updated_at ON control.tenant_branding;
CREATE TRIGGER set_updated_at
BEFORE UPDATE ON control.tenant_branding
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();

ALTER TABLE control.tenant_branding ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.tenant_branding FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_branding_customer_access
ON control.tenant_branding;
CREATE POLICY tenant_branding_customer_access
ON control.tenant_branding FOR SELECT TO ncp_control_app
USING (tenant_id = control.current_tenant_id());

DROP POLICY IF EXISTS tenant_branding_msp_access
ON control.tenant_branding;
CREATE POLICY tenant_branding_msp_access
ON control.tenant_branding FOR ALL TO ncp_msp_app
USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS tenant_branding_public_worker_access
ON control.tenant_branding;
CREATE POLICY tenant_branding_public_worker_access
ON control.tenant_branding FOR SELECT TO ncp_public_worker
USING (EXISTS (
    SELECT 1 FROM control.tenants tenant
    WHERE tenant.id = tenant_id AND tenant.environment = 'public'
));

DROP POLICY IF EXISTS tenant_branding_gov_worker_access
ON control.tenant_branding;
CREATE POLICY tenant_branding_gov_worker_access
ON control.tenant_branding FOR SELECT TO ncp_gov_worker
USING (EXISTS (
    SELECT 1 FROM control.tenants tenant
    WHERE tenant.id = tenant_id AND tenant.environment = 'gov'
));

GRANT SELECT ON control.tenant_branding TO
    ncp_control_app, ncp_public_worker, ncp_gov_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON control.tenant_branding TO ncp_msp_app;

INSERT INTO control.schema_versions (version, description)
VALUES ('150', 'Per-tenant customer logo branding')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
