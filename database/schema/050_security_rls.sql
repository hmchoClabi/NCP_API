\set ON_ERROR_STOP on

GRANT USAGE ON SCHEMA control TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;
GRANT USAGE ON SCHEMA public_data TO
    ncp_control_app,
    ncp_public_worker,
    ncp_msp_app;
GRANT USAGE ON SCHEMA gov_data TO
    ncp_control_app,
    ncp_gov_worker,
    ncp_msp_app;
GRANT USAGE ON SCHEMA audit TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;

GRANT EXECUTE ON FUNCTION control.current_tenant_id() TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;
GRANT EXECUTE ON FUNCTION control.current_actor_id() TO
    ncp_control_app,
    ncp_msp_app;

GRANT SELECT, INSERT, UPDATE ON control.users TO ncp_control_app, ncp_msp_app;
GRANT SELECT ON control.platform_roles TO ncp_control_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON control.platform_roles TO ncp_msp_app;
GRANT SELECT ON control.schema_versions TO ncp_msp_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    control.tenants,
    control.memberships,
    control.credential_refs,
    control.report_schedules,
    control.report_runs,
    control.report_artifacts,
    control.collection_errors,
    control.daily_customer_facts,
    control.email_recipients,
    control.email_deliveries,
    control.event_cases,
    control.event_case_comments
TO ncp_control_app, ncp_msp_app;

GRANT SELECT ON control.tenants, control.credential_refs TO
    ncp_public_worker,
    ncp_gov_worker;
GRANT SELECT, INSERT, UPDATE ON
    control.report_runs,
    control.report_artifacts,
    control.collection_errors,
    control.daily_customer_facts,
    control.email_deliveries,
    control.event_cases
TO ncp_public_worker, ncp_gov_worker;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public_data
TO ncp_control_app, ncp_public_worker, ncp_msp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gov_data
TO ncp_control_app, ncp_gov_worker, ncp_msp_app;

GRANT INSERT ON ALL TABLES IN SCHEMA audit TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO ncp_msp_app;

ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA public_data
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO
    ncp_control_app,
    ncp_public_worker,
    ncp_msp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA gov_data
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO
    ncp_control_app,
    ncp_gov_worker,
    ncp_msp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA audit
GRANT INSERT ON TABLES TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;

ALTER TABLE control.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.tenants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_customer_access ON control.tenants;
CREATE POLICY tenant_customer_access ON control.tenants
    FOR ALL TO ncp_control_app
    USING (id = control.current_tenant_id())
    WITH CHECK (id = control.current_tenant_id());
DROP POLICY IF EXISTS tenant_msp_access ON control.tenants;
CREATE POLICY tenant_msp_access ON control.tenants
    FOR ALL TO ncp_msp_app
    USING (true)
    WITH CHECK (true);
DROP POLICY IF EXISTS tenant_public_worker_access ON control.tenants;
CREATE POLICY tenant_public_worker_access ON control.tenants
    FOR SELECT TO ncp_public_worker
    USING (environment = 'public');
DROP POLICY IF EXISTS tenant_gov_worker_access ON control.tenants;
CREATE POLICY tenant_gov_worker_access ON control.tenants
    FOR SELECT TO ncp_gov_worker
    USING (environment = 'gov');

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'memberships',
        'credential_refs',
        'report_schedules',
        'report_runs',
        'report_artifacts',
        'collection_errors',
        'daily_customer_facts',
        'email_recipients',
        'email_deliveries',
        'event_cases',
        'event_case_comments'
    ]
    LOOP
        EXECUTE format('ALTER TABLE control.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE control.%I FORCE ROW LEVEL SECURITY', table_name);

        EXECUTE format('DROP POLICY IF EXISTS tenant_customer_access ON control.%I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_customer_access ON control.%I '
            'FOR ALL TO ncp_control_app '
            'USING (tenant_id = control.current_tenant_id()) '
            'WITH CHECK (tenant_id = control.current_tenant_id())',
            table_name
        );

        EXECUTE format('DROP POLICY IF EXISTS tenant_msp_access ON control.%I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_msp_access ON control.%I '
            'FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true)',
            table_name
        );

        EXECUTE format('DROP POLICY IF EXISTS tenant_public_worker_access ON control.%I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_public_worker_access ON control.%I '
            'FOR ALL TO ncp_public_worker '
            'USING (EXISTS ('
            'SELECT 1 FROM control.tenants t '
            'WHERE t.id = tenant_id AND t.environment = ''public'')) '
            'WITH CHECK (EXISTS ('
            'SELECT 1 FROM control.tenants t '
            'WHERE t.id = tenant_id AND t.environment = ''public''))',
            table_name
        );

        EXECUTE format('DROP POLICY IF EXISTS tenant_gov_worker_access ON control.%I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_gov_worker_access ON control.%I '
            'FOR ALL TO ncp_gov_worker '
            'USING (EXISTS ('
            'SELECT 1 FROM control.tenants t '
            'WHERE t.id = tenant_id AND t.environment = ''gov'')) '
            'WITH CHECK (EXISTS ('
            'SELECT 1 FROM control.tenants t '
            'WHERE t.id = tenant_id AND t.environment = ''gov''))',
            table_name
        );
    END LOOP;
END;
$$;

DO $$
DECLARE
    data_schema text;
    table_name text;
    worker_role text;
BEGIN
    FOREACH data_schema IN ARRAY ARRAY['public_data', 'gov_data']
    LOOP
        worker_role := CASE
            WHEN data_schema = 'public_data' THEN 'ncp_public_worker'
            ELSE 'ncp_gov_worker'
        END;

        FOREACH table_name IN ARRAY ARRAY[
            'report_snapshots',
            'insight_events',
            'activity_events',
            'metric_series',
            'metric_summaries',
            'cost_details',
            'raw_payload_refs'
        ]
        LOOP
            EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', data_schema, table_name);
            EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', data_schema, table_name);

            EXECUTE format(
                'DROP POLICY IF EXISTS tenant_customer_access ON %I.%I',
                data_schema,
                table_name
            );
            EXECUTE format(
                'CREATE POLICY tenant_customer_access ON %I.%I '
                'FOR ALL TO ncp_control_app '
                'USING (tenant_id = control.current_tenant_id()) '
                'WITH CHECK (tenant_id = control.current_tenant_id())',
                data_schema,
                table_name
            );

            EXECUTE format(
                'DROP POLICY IF EXISTS tenant_msp_access ON %I.%I',
                data_schema,
                table_name
            );
            EXECUTE format(
                'CREATE POLICY tenant_msp_access ON %I.%I '
                'FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true)',
                data_schema,
                table_name
            );

            EXECUTE format(
                'DROP POLICY IF EXISTS environment_worker_access ON %I.%I',
                data_schema,
                table_name
            );
            EXECUTE format(
                'CREATE POLICY environment_worker_access ON %I.%I '
                'FOR ALL TO %I USING (true) WITH CHECK (true)',
                data_schema,
                table_name,
                worker_role
            );
        END LOOP;
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('050', 'schema grants, environment roles and tenant row-level security')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
