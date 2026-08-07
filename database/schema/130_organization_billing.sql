\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.organization_members (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    source_cloud_account_id uuid NOT NULL,
    member_no varchar(30) NOT NULL,
    display_name varchar(200) NOT NULL,
    organization_no varchar(30),
    group_no varchar(30),
    group_path varchar(500),
    is_master boolean NOT NULL DEFAULT false,
    status varchar(30) NOT NULL DEFAULT 'JOIN',
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT organization_members_account_fk FOREIGN KEY (
        source_cloud_account_id, tenant_id
    ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
    UNIQUE (source_cloud_account_id, member_no)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON control.organization_members TO
    ncp_control_app, ncp_public_worker, ncp_gov_worker, ncp_msp_app;
ALTER TABLE control.organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.organization_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS organization_members_customer_access ON control.organization_members;
CREATE POLICY organization_members_customer_access
ON control.organization_members FOR ALL TO ncp_control_app
USING (tenant_id = control.current_tenant_id())
WITH CHECK (tenant_id = control.current_tenant_id());
DROP POLICY IF EXISTS organization_members_msp_access ON control.organization_members;
CREATE POLICY organization_members_msp_access
ON control.organization_members FOR ALL TO ncp_msp_app
USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS organization_members_public_worker_access ON control.organization_members;
CREATE POLICY organization_members_public_worker_access
ON control.organization_members FOR ALL TO ncp_public_worker
USING (EXISTS (
    SELECT 1 FROM control.cloud_accounts account
    WHERE account.id = source_cloud_account_id AND account.environment = 'public'
)) WITH CHECK (EXISTS (
    SELECT 1 FROM control.cloud_accounts account
    WHERE account.id = source_cloud_account_id AND account.environment = 'public'
));
DROP POLICY IF EXISTS organization_members_gov_worker_access ON control.organization_members;
CREATE POLICY organization_members_gov_worker_access
ON control.organization_members FOR ALL TO ncp_gov_worker
USING (EXISTS (
    SELECT 1 FROM control.cloud_accounts account
    WHERE account.id = source_cloud_account_id AND account.environment = 'gov'
)) WITH CHECK (EXISTS (
    SELECT 1 FROM control.cloud_accounts account
    WHERE account.id = source_cloud_account_id AND account.environment = 'gov'
));

DO $$
DECLARE
    data_schema text;
    environment_name text;
    worker_role text;
BEGIN
    FOREACH data_schema IN ARRAY ARRAY['public_data', 'gov_data'] LOOP
        environment_name := CASE WHEN data_schema = 'public_data' THEN 'public' ELSE 'gov' END;
        worker_role := CASE WHEN data_schema = 'public_data' THEN 'ncp_public_worker' ELSE 'ncp_gov_worker' END;
        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.billing_account_cost_facts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                cloud_account_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                member_no varchar(30) NOT NULL,
                display_name varchar(200) NOT NULL,
                is_master boolean NOT NULL DEFAULT false,
                cost_type varchar(40) NOT NULL,
                status varchar(30) NOT NULL,
                period_start date NOT NULL,
                period_end date NOT NULL,
                subtotal_amount numeric(20, 4),
                vat_amount numeric(20, 4),
                total_amount numeric(20, 4),
                confidence varchar(30) NOT NULL,
                service_costs jsonb NOT NULL DEFAULT '[]'::jsonb,
                details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT billing_account_facts_environment_check CHECK (environment = %L),
                CONSTRAINT billing_account_facts_services_check CHECK (jsonb_typeof(service_costs) = 'array'),
                CONSTRAINT billing_account_facts_run_fk FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment) ON DELETE CASCADE,
                CONSTRAINT billing_account_facts_account_fk FOREIGN KEY (cloud_account_id, tenant_id)
                    REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
                UNIQUE (report_run_id, member_no, cost_type)
            )
        $ddl$, data_schema, environment_name, environment_name);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I.billing_account_cost_facts TO ncp_control_app, %I, ncp_msp_app', data_schema, worker_role);
        EXECUTE format('ALTER TABLE %I.billing_account_cost_facts ENABLE ROW LEVEL SECURITY', data_schema);
        EXECUTE format('ALTER TABLE %I.billing_account_cost_facts FORCE ROW LEVEL SECURITY', data_schema);
        EXECUTE format('DROP POLICY IF EXISTS billing_account_facts_customer_access ON %I.billing_account_cost_facts', data_schema);
        EXECUTE format('CREATE POLICY billing_account_facts_customer_access ON %I.billing_account_cost_facts FOR ALL TO ncp_control_app USING (tenant_id = control.current_tenant_id()) WITH CHECK (tenant_id = control.current_tenant_id())', data_schema);
        EXECUTE format('DROP POLICY IF EXISTS billing_account_facts_msp_access ON %I.billing_account_cost_facts', data_schema);
        EXECUTE format('CREATE POLICY billing_account_facts_msp_access ON %I.billing_account_cost_facts FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true)', data_schema);
        EXECUTE format('DROP POLICY IF EXISTS billing_account_facts_worker_access ON %I.billing_account_cost_facts', data_schema);
        EXECUTE format('CREATE POLICY billing_account_facts_worker_access ON %I.billing_account_cost_facts FOR ALL TO %I USING (true) WITH CHECK (true)', data_schema, worker_role);
    END LOOP;
END $$;

INSERT INTO control.schema_versions (version, description)
VALUES ('130', 'Organization member discovery and account-level billing facts')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;
