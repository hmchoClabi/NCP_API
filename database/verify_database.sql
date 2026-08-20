\set ON_ERROR_STOP on

DO $$
DECLARE
    missing_schemas text[];
    missing_roles text[];
    table_count integer;
    rls_missing_count integer;
BEGIN
    SELECT array_agg(expected.schema_name)
    INTO missing_schemas
    FROM unnest(ARRAY['control', 'public_data', 'gov_data', 'audit'])
        AS expected(schema_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata actual
        WHERE actual.schema_name = expected.schema_name
    );

    IF missing_schemas IS NOT NULL THEN
        RAISE EXCEPTION 'Missing schemas: %', missing_schemas;
    END IF;

    SELECT array_agg(expected.role_name)
    INTO missing_roles
    FROM unnest(ARRAY[
        'ncp_schema_owner',
        'ncp_control_app',
        'ncp_public_worker',
        'ncp_gov_worker',
        'ncp_msp_app'
    ]) AS expected(role_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles actual
        WHERE actual.rolname = expected.role_name
    );

    IF missing_roles IS NOT NULL THEN
        RAISE EXCEPTION 'Missing roles: %', missing_roles;
    END IF;

    SELECT count(*)
    INTO table_count
    FROM information_schema.tables
    WHERE table_schema IN ('control', 'public_data', 'gov_data', 'audit')
      AND table_type = 'BASE TABLE';

    IF table_count < 37 THEN
        RAISE EXCEPTION 'Expected at least 37 tables, found %', table_count;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'control'
          AND tablename = 'tenant_branding'
          AND rowsecurity
    ) THEN
        RAISE EXCEPTION 'Tenant branding table or RLS is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'control'
          AND tablename = 'policy_exceptions'
          AND rowsecurity
    ) THEN
        RAISE EXCEPTION 'Policy exceptions table or RLS is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'control'
          AND tablename = 'artifact_cleanup_outbox'
          AND rowsecurity
    ) THEN
        RAISE EXCEPTION 'Artifact cleanup outbox or RLS is missing';
    END IF;

    IF NOT has_table_privilege(
        'ncp_msp_app', 'control.artifact_cleanup_outbox', 'SELECT'
    ) OR NOT has_table_privilege(
        'ncp_msp_app', 'control.artifact_cleanup_outbox', 'INSERT'
    ) OR NOT has_table_privilege(
        'ncp_msp_app', 'control.artifact_cleanup_outbox', 'UPDATE'
    ) OR NOT has_table_privilege(
        'ncp_msp_app', 'control.artifact_cleanup_outbox', 'DELETE'
    ) THEN
        RAISE EXCEPTION 'MSP role cannot process the artifact cleanup outbox';
    END IF;

    IF has_table_privilege(
        'ncp_public_worker', 'control.artifact_cleanup_outbox', 'SELECT'
    ) OR has_table_privilege(
        'ncp_gov_worker', 'control.artifact_cleanup_outbox', 'SELECT'
    ) THEN
        RAISE EXCEPTION 'Environment workers can access artifact cleanup outbox';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'control'
          AND tablename = 'event_cases'
          AND policyname = 'tenant_msp_access'
          AND qual ILIKE '%current_tenant_id%'
          AND with_check ILIKE '%current_tenant_id%'
    ) THEN
        RAISE EXCEPTION 'Event case MSP tenant RLS is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'control'
          AND tablename = 'policy_exceptions'
          AND policyname = 'policy_exceptions_msp_access'
          AND qual ILIKE '%app.environment_scope%'
          AND with_check ILIKE '%app.environment_scope%'
    ) THEN
        RAISE EXCEPTION 'Policy exception MSP environment RLS is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.event_cases'::regclass
          AND conname = 'event_cases_tenant_environment_fk'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.event_cases'::regclass
          AND conname = 'event_cases_latest_run_tenant_fk'
    ) THEN
        RAISE EXCEPTION 'Event case tenant boundary constraints are missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.daily_account_facts'::regclass
          AND conname = 'daily_account_facts_pkey'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'control.daily_account_facts'::regclass
          AND conname = 'daily_account_facts_cloud_account_tenant_fk'
    ) THEN
        RAISE EXCEPTION 'Daily fact account boundary constraints are missing';
    END IF;

    IF has_table_privilege(
        'ncp_control_app', 'control.policy_exceptions', 'INSERT'
    ) OR has_table_privilege(
        'ncp_control_app', 'control.policy_exceptions', 'UPDATE'
    ) OR has_table_privilege(
        'ncp_control_app', 'control.policy_exceptions', 'DELETE'
    ) THEN
        RAISE EXCEPTION 'Customer role can mutate policy exceptions';
    END IF;

    SELECT count(*)
    INTO rls_missing_count
    FROM pg_tables
    WHERE schemaname IN ('public_data', 'gov_data')
      AND NOT rowsecurity;

    IF rls_missing_count > 0 THEN
        RAISE EXCEPTION '% environment tables do not have RLS enabled', rls_missing_count;
    END IF;
END;
$$;

BEGIN;

INSERT INTO control.tenants (
    id,
    customer_code,
    customer_name,
    environment,
    region
)
VALUES
    (
        '00000000-0000-0000-0000-000000000101',
        'verify-public',
        'Verification Public Tenant',
        'public',
        'KR'
    ),
    (
        '00000000-0000-0000-0000-000000000102',
        'verify-gov',
        'Verification GOV Tenant',
        'gov',
        'KRS'
    )
ON CONFLICT (id) DO NOTHING;

SET LOCAL ROLE ncp_control_app;
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000101';

DO $$
BEGIN
    IF (SELECT count(*) FROM control.tenants) <> 1 THEN
        RAISE EXCEPTION 'Customer RLS did not isolate the selected tenant';
    END IF;
END;
$$;

RESET ROLE;
SET LOCAL ROLE ncp_public_worker;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM control.tenants WHERE environment <> 'public'
    ) OR NOT EXISTS (
        SELECT 1 FROM control.tenants
        WHERE id = '00000000-0000-0000-0000-000000000101'
    ) THEN
        RAISE EXCEPTION 'Public worker tenant policy did not isolate public tenants';
    END IF;

    BEGIN
        PERFORM count(*) FROM gov_data.insight_events;
        RAISE EXCEPTION 'Public worker unexpectedly accessed gov_data';
    EXCEPTION
        WHEN insufficient_privilege THEN
            NULL;
    END;
END;
$$;

RESET ROLE;
SET LOCAL ROLE ncp_gov_worker;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM control.tenants WHERE environment <> 'gov'
    ) OR NOT EXISTS (
        SELECT 1 FROM control.tenants
        WHERE id = '00000000-0000-0000-0000-000000000102'
    ) THEN
        RAISE EXCEPTION 'GOV worker tenant policy did not isolate GOV tenants';
    END IF;

    BEGIN
        PERFORM count(*) FROM public_data.insight_events;
        RAISE EXCEPTION 'GOV worker unexpectedly accessed public_data';
    EXCEPTION
        WHEN insufficient_privilege THEN
            NULL;
    END;
END;
$$;

RESET ROLE;
ROLLBACK;

SELECT
    schemaname,
    count(*) AS table_count,
    count(*) FILTER (WHERE rowsecurity) AS rls_table_count
FROM pg_tables
WHERE schemaname IN ('control', 'public_data', 'gov_data', 'audit')
GROUP BY schemaname
ORDER BY schemaname;

SELECT version, description, applied_at
FROM control.schema_versions
ORDER BY version;
