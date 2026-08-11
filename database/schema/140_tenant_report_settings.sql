\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS control.tenant_report_settings (
    tenant_id uuid PRIMARY KEY REFERENCES control.tenants(id) ON DELETE CASCADE,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT tenant_report_settings_object_check CHECK (
        jsonb_typeof(settings) = 'object'
    )
);

INSERT INTO control.tenant_report_settings (tenant_id, settings)
SELECT id, '{}'::jsonb
FROM control.tenants
ON CONFLICT (tenant_id) DO NOTHING;

DROP TRIGGER IF EXISTS set_updated_at ON control.tenant_report_settings;
CREATE TRIGGER set_updated_at
BEFORE UPDATE ON control.tenant_report_settings
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();

ALTER TABLE control.tenant_report_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.tenant_report_settings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_report_settings_customer_access
ON control.tenant_report_settings;
CREATE POLICY tenant_report_settings_customer_access
ON control.tenant_report_settings FOR SELECT TO ncp_control_app
USING (tenant_id = control.current_tenant_id());

DROP POLICY IF EXISTS tenant_report_settings_msp_access
ON control.tenant_report_settings;
CREATE POLICY tenant_report_settings_msp_access
ON control.tenant_report_settings FOR ALL TO ncp_msp_app
USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS tenant_report_settings_public_worker_access
ON control.tenant_report_settings;
CREATE POLICY tenant_report_settings_public_worker_access
ON control.tenant_report_settings FOR SELECT TO ncp_public_worker
USING (EXISTS (
    SELECT 1 FROM control.tenants tenant
    WHERE tenant.id = tenant_id AND tenant.environment = 'public'
));

DROP POLICY IF EXISTS tenant_report_settings_gov_worker_access
ON control.tenant_report_settings;
CREATE POLICY tenant_report_settings_gov_worker_access
ON control.tenant_report_settings FOR SELECT TO ncp_gov_worker
USING (EXISTS (
    SELECT 1 FROM control.tenants tenant
    WHERE tenant.id = tenant_id AND tenant.environment = 'gov'
));

GRANT SELECT ON control.tenant_report_settings TO
    ncp_control_app, ncp_public_worker, ncp_gov_worker;
GRANT SELECT, INSERT, UPDATE ON control.tenant_report_settings TO
    ncp_msp_app;

INSERT INTO control.schema_versions (version, description)
VALUES ('140', 'Per-tenant report content settings')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
