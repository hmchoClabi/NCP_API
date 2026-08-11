\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    data_schema text;
    environment_name text;
    worker_role text;
BEGIN
    FOREACH data_schema IN ARRAY ARRAY['public_data', 'gov_data']
    LOOP
        environment_name := CASE
            WHEN data_schema = 'public_data' THEN 'public'
            ELSE 'gov'
        END;
        worker_role := CASE
            WHEN data_schema = 'public_data' THEN 'ncp_public_worker'
            ELSE 'ncp_gov_worker'
        END;

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.network_configuration_snapshots (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                cloud_account_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                captured_at timestamptz NOT NULL,
                period_start timestamptz NOT NULL,
                period_end timestamptz NOT NULL,
                end_exclusive boolean NOT NULL DEFAULT true,
                source varchar(40) NOT NULL,
                schema_version varchar(40) NOT NULL,
                configuration jsonb NOT NULL,
                capture_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                content_hash_sha256 char(64) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT network_configuration_snapshots_environment_check
                    CHECK (environment = %L),
                CONSTRAINT network_configuration_snapshots_period_check
                    CHECK (period_start < period_end),
                CONSTRAINT network_configuration_snapshots_source_check
                    CHECK (source = 'REPORT_GENERATION'),
                CONSTRAINT network_configuration_snapshots_json_array_check
                    CHECK (jsonb_typeof(configuration) = 'array'),
                CONSTRAINT network_configuration_snapshots_metadata_check
                    CHECK (jsonb_typeof(capture_metadata) = 'object'),
                CONSTRAINT network_configuration_snapshots_hash_check
                    CHECK (content_hash_sha256 ~ '^[0-9a-f]{64}$'),
                CONSTRAINT network_configuration_snapshots_run_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE,
                CONSTRAINT network_configuration_snapshots_account_fk
                    FOREIGN KEY (cloud_account_id, tenant_id)
                    REFERENCES control.cloud_accounts(id, tenant_id)
                    ON DELETE CASCADE,
                UNIQUE (report_run_id)
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS network_configuration_snapshots_lookup_idx '
            'ON %I.network_configuration_snapshots '
            '(tenant_id, cloud_account_id, captured_at DESC)',
            data_schema
        );

        EXECUTE format(
            'GRANT SELECT, INSERT, DELETE '
            'ON %I.network_configuration_snapshots '
            'TO ncp_control_app, %I, ncp_msp_app',
            data_schema,
            worker_role
        );

        EXECUTE format(
            'ALTER TABLE %I.network_configuration_snapshots '
            'ENABLE ROW LEVEL SECURITY',
            data_schema
        );
        EXECUTE format(
            'ALTER TABLE %I.network_configuration_snapshots '
            'FORCE ROW LEVEL SECURITY',
            data_schema
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS tenant_customer_access '
            'ON %I.network_configuration_snapshots',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY tenant_customer_access '
            'ON %I.network_configuration_snapshots '
            'FOR ALL TO ncp_control_app '
            'USING (tenant_id = control.current_tenant_id()) '
            'WITH CHECK (tenant_id = control.current_tenant_id())',
            data_schema
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS tenant_msp_access '
            'ON %I.network_configuration_snapshots',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY tenant_msp_access '
            'ON %I.network_configuration_snapshots '
            'FOR ALL TO ncp_msp_app '
            'USING (true) WITH CHECK (true)',
            data_schema
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS environment_worker_access '
            'ON %I.network_configuration_snapshots',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY environment_worker_access '
            'ON %I.network_configuration_snapshots '
            'FOR ALL TO %I '
            'USING (true) WITH CHECK (true)',
            data_schema,
            worker_role
        );
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('170', 'Report-generation network configuration snapshots')
ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
