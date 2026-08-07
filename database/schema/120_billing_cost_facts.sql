\set ON_ERROR_STOP on

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
            CREATE TABLE IF NOT EXISTS %I.billing_cost_facts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                cloud_account_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                cost_type varchar(40) NOT NULL,
                status varchar(30) NOT NULL,
                period_start date NOT NULL,
                period_end date NOT NULL,
                coverage_start date,
                coverage_end date,
                calculated_at timestamptz NOT NULL,
                subtotal_amount numeric(20, 4),
                discount_amount numeric(20, 4),
                vat_amount numeric(20, 4),
                total_amount numeric(20, 4),
                currency char(3) NOT NULL DEFAULT 'KRW',
                amount_basis varchar(60) NOT NULL,
                includes_discount boolean NOT NULL DEFAULT false,
                includes_vat boolean NOT NULL DEFAULT false,
                confidence varchar(30) NOT NULL,
                excluded_item_count integer NOT NULL DEFAULT 0,
                source_api varchar(500),
                calculation_version varchar(40) NOT NULL,
                details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT billing_cost_facts_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT billing_cost_facts_type_check CHECK (
                    cost_type IN (
                        'CONFIRMED',
                        'PERIOD_ESTIMATE',
                        'MONTH_TO_DATE_ESTIMATE',
                        'MONTH_END_PROJECTION'
                    )
                ),
                CONSTRAINT billing_cost_facts_status_check CHECK (
                    status IN ('AVAILABLE', 'UNAVAILABLE')
                ),
                CONSTRAINT billing_cost_facts_period_check CHECK (
                    period_start <= period_end
                    AND (
                        (coverage_start IS NULL AND coverage_end IS NULL)
                        OR (
                            coverage_start IS NOT NULL
                            AND coverage_end IS NOT NULL
                            AND coverage_start <= coverage_end
                        )
                    )
                ),
                CONSTRAINT billing_cost_facts_confidence_check CHECK (
                    confidence IN (
                        'CONFIRMED', 'VERIFIED_ESTIMATE',
                        'PARTIAL', 'UNAVAILABLE'
                    )
                ),
                CONSTRAINT billing_cost_facts_excluded_count_check CHECK (
                    excluded_item_count >= 0
                ),
                CONSTRAINT billing_cost_facts_details_check CHECK (
                    jsonb_typeof(details) = 'object'
                ),
                CONSTRAINT billing_cost_facts_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE,
                CONSTRAINT billing_cost_facts_account_tenant_fk
                    FOREIGN KEY (cloud_account_id, tenant_id)
                    REFERENCES control.cloud_accounts(id, tenant_id)
                    ON DELETE CASCADE,
                UNIQUE (report_run_id, cost_type)
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS billing_cost_facts_tenant_period_idx '
            'ON %I.billing_cost_facts '
            '(tenant_id, cloud_account_id, period_end DESC, cost_type)',
            data_schema
        );

        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON %I.billing_cost_facts '
            'TO ncp_control_app, %I, ncp_msp_app',
            data_schema,
            worker_role
        );

        EXECUTE format(
            'ALTER TABLE %I.billing_cost_facts ENABLE ROW LEVEL SECURITY',
            data_schema
        );
        EXECUTE format(
            'ALTER TABLE %I.billing_cost_facts FORCE ROW LEVEL SECURITY',
            data_schema
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS tenant_customer_access ON %I.billing_cost_facts',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY tenant_customer_access ON %I.billing_cost_facts '
            'FOR ALL TO ncp_control_app '
            'USING (tenant_id = control.current_tenant_id()) '
            'WITH CHECK (tenant_id = control.current_tenant_id())',
            data_schema
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS tenant_msp_access ON %I.billing_cost_facts',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY tenant_msp_access ON %I.billing_cost_facts '
            'FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true)',
            data_schema
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS environment_worker_access ON %I.billing_cost_facts',
            data_schema
        );
        EXECUTE format(
            'CREATE POLICY environment_worker_access ON %I.billing_cost_facts '
            'FOR ALL TO %I USING (true) WITH CHECK (true)',
            data_schema,
            worker_role
        );
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('120', 'period-aware confirmed, estimated and projected billing cost facts')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
