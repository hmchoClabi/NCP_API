\set ON_ERROR_STOP on

DO $$
DECLARE
    data_schema text;
    environment_name text;
BEGIN
    FOREACH data_schema IN ARRAY ARRAY['public_data', 'gov_data']
    LOOP
        environment_name := CASE
            WHEN data_schema = 'public_data' THEN 'public'
            ELSE 'gov'
        END;

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.report_snapshots (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                schema_version varchar(40) NOT NULL,
                collector_version varchar(80),
                normalizer_version varchar(80),
                renderer_version varchar(80),
                normalized_data jsonb NOT NULL,
                content_hash_sha256 char(64),
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT report_snapshots_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT report_snapshots_json_object_check CHECK (
                    jsonb_typeof(normalized_data) = 'object'
                ),
                CONSTRAINT report_snapshots_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE,
                UNIQUE (report_run_id)
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.insight_events (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                source_event_id varchar(255),
                occurred_at timestamptz NOT NULL,
                ended_at timestamptz,
                severity varchar(20),
                service_name varchar(200),
                resource_id varchar(255),
                resource_name varchar(500),
                resource_type varchar(200),
                rule_id varchar(255),
                rule_name varchar(500),
                metric varchar(255),
                operator varchar(20),
                criteria varchar(255),
                detect_value varchar(255),
                unit varchar(50),
                aggregation varchar(30),
                interval_name varchar(30),
                notification_status varchar(30),
                in_maintenance boolean,
                resource_deleted boolean,
                details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT insight_events_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT insight_events_details_object_check CHECK (
                    jsonb_typeof(details) = 'object'
                ),
                CONSTRAINT insight_events_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.activity_events (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                source_event_id varchar(255),
                occurred_at timestamptz NOT NULL,
                account_name varchar(320),
                account_type varchar(100),
                service_name varchar(200),
                resource_type varchar(200),
                resource_id varchar(500),
                resource_name varchar(500),
                action_name varchar(300),
                result varchar(50),
                source_ip inet,
                details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT activity_events_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT activity_events_details_object_check CHECK (
                    jsonb_typeof(details) = 'object'
                ),
                CONSTRAINT activity_events_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.metric_series (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                resource_id varchar(255) NOT NULL,
                resource_name varchar(500),
                metric_group varchar(30) NOT NULL,
                metric_name varchar(255) NOT NULL,
                dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
                interval_name varchar(30),
                aggregation varchar(30),
                period_start timestamptz NOT NULL,
                period_end timestamptz NOT NULL,
                points jsonb,
                artifact_uri text,
                point_count integer NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT metric_series_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT metric_series_group_check CHECK (
                    metric_group IN ('CPU', 'MEM', 'ROOT_DISK', 'DATA_DISK', 'OTHER')
                ),
                CONSTRAINT metric_series_period_check CHECK (
                    period_start < period_end
                ),
                CONSTRAINT metric_series_points_check CHECK (
                    points IS NULL OR jsonb_typeof(points) = 'array'
                ),
                CONSTRAINT metric_series_dimensions_check CHECK (
                    jsonb_typeof(dimensions) = 'object'
                ),
                CONSTRAINT metric_series_storage_check CHECK (
                    points IS NOT NULL OR artifact_uri IS NOT NULL
                ),
                CONSTRAINT metric_series_count_check CHECK (point_count >= 0),
                CONSTRAINT metric_series_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.metric_summaries (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                resource_id varchar(255) NOT NULL,
                resource_name varchar(500),
                metric_group varchar(30) NOT NULL,
                metric_name varchar(255) NOT NULL,
                mount_name varchar(500),
                minimum numeric(20, 6),
                average numeric(20, 6),
                maximum numeric(20, 6),
                sample_count integer NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT metric_summaries_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT metric_summaries_group_check CHECK (
                    metric_group IN ('CPU', 'MEM', 'ROOT_DISK', 'DATA_DISK', 'OTHER')
                ),
                CONSTRAINT metric_summaries_count_check CHECK (sample_count >= 0),
                CONSTRAINT metric_summaries_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.cost_details (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                billing_month char(6) NOT NULL,
                service_name varchar(300) NOT NULL,
                item_name varchar(500),
                item_code varchar(255),
                usage_quantity numeric(30, 10),
                usage_unit varchar(100),
                raw_unit_price numeric(30, 10),
                expected_amount numeric(20, 4),
                confirmed_use_amount numeric(20, 4),
                confirmed_demand_amount numeric(20, 4),
                calculation_method varchar(255),
                calculation_status varchar(100) NOT NULL,
                calculation_details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT cost_details_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT cost_details_billing_month_check CHECK (
                    billing_month ~ '^[0-9]{6}$'
                ),
                CONSTRAINT cost_details_json_object_check CHECK (
                    jsonb_typeof(calculation_details) = 'object'
                ),
                CONSTRAINT cost_details_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format($ddl$
            CREATE TABLE IF NOT EXISTS %I.raw_payload_refs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                report_run_id uuid NOT NULL,
                tenant_id uuid NOT NULL,
                environment varchar(10) NOT NULL DEFAULT %L,
                collector varchar(100) NOT NULL,
                storage_uri text NOT NULL,
                checksum_sha256 char(64),
                byte_size bigint,
                content_encoding varchar(50),
                contains_sensitive_data boolean NOT NULL DEFAULT true,
                created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                CONSTRAINT raw_payload_refs_environment_check CHECK (
                    environment = %L
                ),
                CONSTRAINT raw_payload_refs_size_check CHECK (
                    byte_size IS NULL OR byte_size >= 0
                ),
                CONSTRAINT raw_payload_refs_run_tenant_environment_fk
                    FOREIGN KEY (report_run_id, tenant_id, environment)
                    REFERENCES control.report_runs(id, tenant_id, environment)
                    ON DELETE CASCADE,
                UNIQUE (report_run_id, collector, storage_uri)
            )
        $ddl$, data_schema, environment_name, environment_name);

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS insight_events_tenant_time_idx '
            'ON %I.insight_events (tenant_id, occurred_at DESC)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS insight_events_open_severity_idx '
            'ON %I.insight_events (severity, occurred_at DESC)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS insight_events_details_gin_idx '
            'ON %I.insight_events USING gin (details)',
            data_schema
        );
        EXECUTE format(
            'CREATE UNIQUE INDEX IF NOT EXISTS insight_events_source_uidx '
            'ON %I.insight_events (report_run_id, source_event_id, occurred_at) '
            'WHERE source_event_id IS NOT NULL',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS activity_events_tenant_time_idx '
            'ON %I.activity_events (tenant_id, occurred_at DESC)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS activity_events_result_idx '
            'ON %I.activity_events (result, occurred_at DESC)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS activity_events_details_gin_idx '
            'ON %I.activity_events USING gin (details)',
            data_schema
        );
        EXECUTE format(
            'CREATE UNIQUE INDEX IF NOT EXISTS activity_events_source_uidx '
            'ON %I.activity_events (report_run_id, source_event_id, occurred_at) '
            'WHERE source_event_id IS NOT NULL',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS metric_series_run_group_idx '
            'ON %I.metric_series (report_run_id, metric_group)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS metric_summaries_run_group_idx '
            'ON %I.metric_summaries (report_run_id, metric_group)',
            data_schema
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS cost_details_tenant_month_idx '
            'ON %I.cost_details (tenant_id, billing_month, service_name)',
            data_schema
        );
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('030', 'public and gov report detail tables')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
