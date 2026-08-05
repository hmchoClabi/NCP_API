\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_code varchar(80) NOT NULL,
    customer_name varchar(200) NOT NULL,
    environment varchar(10) NOT NULL,
    region varchar(20) NOT NULL,
    timezone varchar(64) NOT NULL DEFAULT 'Asia/Seoul',
    worker_group varchar(100),
    status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    primary_contact_email varchar(320),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT tenants_customer_code_format CHECK (
        customer_code ~ '^[a-z0-9][a-z0-9_-]{1,78}[a-z0-9]$'
    ),
    CONSTRAINT tenants_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT tenants_status_check CHECK (
        status IN ('ACTIVE', 'SUSPENDED', 'ONBOARDING', 'OFFBOARDED')
    ),
    CONSTRAINT tenants_metadata_object_check CHECK (
        jsonb_typeof(metadata) = 'object'
    ),
    UNIQUE (customer_code),
    UNIQUE (id, environment)
);

CREATE TABLE IF NOT EXISTS control.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email varchar(320) NOT NULL,
    password_hash text,
    display_name varchar(200) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'INVITED',
    mfa_enabled boolean NOT NULL DEFAULT false,
    external_identity_provider varchar(80),
    external_subject varchar(255),
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT users_status_check CHECK (
        status IN ('INVITED', 'ACTIVE', 'LOCKED', 'DISABLED')
    ),
    CONSTRAINT users_auth_method_check CHECK (
        status = 'INVITED'
        OR password_hash IS NOT NULL
        OR (
            external_identity_provider IS NOT NULL
            AND external_subject IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uidx
ON control.users (lower(email));

CREATE UNIQUE INDEX IF NOT EXISTS users_external_identity_uidx
ON control.users (external_identity_provider, external_subject)
WHERE external_identity_provider IS NOT NULL;

CREATE TABLE IF NOT EXISTS control.memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES control.users(id) ON DELETE CASCADE,
    role varchar(30) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT memberships_role_check CHECK (
        role IN ('CUSTOMER_VIEWER', 'CUSTOMER_ADMIN')
    ),
    CONSTRAINT memberships_status_check CHECK (
        status IN ('ACTIVE', 'SUSPENDED')
    ),
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS control.platform_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES control.users(id) ON DELETE CASCADE,
    role varchar(40) NOT NULL,
    environment_scope varchar(10),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT platform_roles_role_check CHECK (
        role IN (
            'MSP_OPERATOR',
            'MSP_ADMIN',
            'SYSTEM_ADMIN',
            'SECURITY_AUDITOR'
        )
    ),
    CONSTRAINT platform_roles_environment_check CHECK (
        environment_scope IS NULL
        OR environment_scope IN ('public', 'gov')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS platform_roles_scope_uidx
ON control.platform_roles (
    user_id,
    role,
    COALESCE(environment_scope, '*')
);

CREATE TABLE IF NOT EXISTS control.credential_refs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL UNIQUE REFERENCES control.tenants(id) ON DELETE CASCADE,
    provider varchar(30) NOT NULL,
    secret_reference text NOT NULL,
    access_key_hint varchar(32),
    status varchar(20) NOT NULL DEFAULT 'PENDING',
    last_verified_at timestamptz,
    last_rotated_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT credential_refs_provider_check CHECK (
        provider IN ('ENV', 'DOCKER_SECRET', 'KMS', 'EXTERNAL_SECRET_MANAGER')
    ),
    CONSTRAINT credential_refs_status_check CHECK (
        status IN ('PENDING', 'VALID', 'INVALID', 'ROTATION_REQUIRED', 'DISABLED')
    ),
    CONSTRAINT credential_refs_no_plaintext_check CHECK (
        secret_reference !~* '(secret[_-]?key|access[_-]?key)\s*='
    ),
    CONSTRAINT credential_refs_reference_format_check CHECK (
        (provider = 'ENV' AND secret_reference ~ '^env://[A-Za-z0-9_./-]+$')
        OR (
            provider = 'DOCKER_SECRET'
            AND secret_reference ~ '^docker-secret://[A-Za-z0-9_./-]+$'
        )
        OR (provider = 'KMS' AND secret_reference ~ '^kms://[^[:space:]]+$')
        OR (
            provider = 'EXTERNAL_SECRET_MANAGER'
            AND secret_reference ~ '^secret://[^[:space:]]+$'
        )
    )
);

ALTER TABLE control.users
DROP CONSTRAINT IF EXISTS users_auth_method_check;
ALTER TABLE control.users
ADD CONSTRAINT users_auth_method_check CHECK (
    status = 'INVITED'
    OR password_hash IS NOT NULL
    OR (
        external_identity_provider IS NOT NULL
        AND external_subject IS NOT NULL
    )
);

ALTER TABLE control.credential_refs
DROP CONSTRAINT IF EXISTS credential_refs_reference_format_check;
ALTER TABLE control.credential_refs
ADD CONSTRAINT credential_refs_reference_format_check CHECK (
    (provider = 'ENV' AND secret_reference ~ '^env://[A-Za-z0-9_./-]+$')
    OR (
        provider = 'DOCKER_SECRET'
        AND secret_reference ~ '^docker-secret://[A-Za-z0-9_./-]+$'
    )
    OR (provider = 'KMS' AND secret_reference ~ '^kms://[^[:space:]]+$')
    OR (
        provider = 'EXTERNAL_SECRET_MANAGER'
        AND secret_reference ~ '^secret://[^[:space:]]+$'
    )
);

CREATE TABLE IF NOT EXISTS control.report_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    report_type varchar(20) NOT NULL,
    cron_expression varchar(100) NOT NULL,
    timezone varchar(64) NOT NULL DEFAULT 'Asia/Seoul',
    enabled boolean NOT NULL DEFAULT true,
    recipient_mode varchar(20) NOT NULL DEFAULT 'CONFIGURED',
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    next_run_at timestamptz,
    last_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT report_schedules_type_check CHECK (
        report_type IN ('DAILY', 'MONTHLY', 'CUSTOM')
    ),
    CONSTRAINT report_schedules_recipient_mode_check CHECK (
        recipient_mode IN ('NONE', 'CONFIGURED')
    ),
    CONSTRAINT report_schedules_config_object_check CHECK (
        jsonb_typeof(config) = 'object'
    ),
    UNIQUE (tenant_id, report_type)
);

CREATE TABLE IF NOT EXISTS control.report_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE RESTRICT,
    environment varchar(10) NOT NULL,
    report_type varchar(20) NOT NULL,
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    end_exclusive boolean NOT NULL DEFAULT true,
    status varchar(30) NOT NULL DEFAULT 'QUEUED',
    trigger_type varchar(20) NOT NULL DEFAULT 'SCHEDULED',
    requested_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    idempotency_key varchar(255) NOT NULL,
    collector_version varchar(80),
    normalizer_version varchar(80),
    renderer_version varchar(80),
    attempt_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT report_runs_tenant_environment_fk FOREIGN KEY (
        tenant_id,
        environment
    ) REFERENCES control.tenants(id, environment),
    CONSTRAINT report_runs_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT report_runs_type_check CHECK (
        report_type IN ('DAILY', 'MONTHLY', 'CUSTOM')
    ),
    CONSTRAINT report_runs_status_check CHECK (
        status IN (
            'QUEUED',
            'RUNNING',
            'PARTIAL_SUCCESS',
            'SUCCESS',
            'FAILED',
            'RETRYING',
            'CANCELLED'
        )
    ),
    CONSTRAINT report_runs_trigger_check CHECK (
        trigger_type IN ('SCHEDULED', 'MANUAL', 'RETRY', 'API')
    ),
    CONSTRAINT report_runs_period_check CHECK (period_start < period_end),
    CONSTRAINT report_runs_count_check CHECK (
        attempt_count >= 0 AND error_count >= 0
    ),
    UNIQUE (idempotency_key),
    UNIQUE (id, tenant_id),
    UNIQUE (id, tenant_id, environment)
);

CREATE INDEX IF NOT EXISTS report_runs_tenant_period_idx
ON control.report_runs (tenant_id, period_start DESC);

CREATE INDEX IF NOT EXISTS report_runs_status_queued_idx
ON control.report_runs (status, queued_at)
WHERE status IN ('QUEUED', 'RETRYING', 'RUNNING');

CREATE TABLE IF NOT EXISTS control.report_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_run_id uuid NOT NULL REFERENCES control.report_runs(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE RESTRICT,
    artifact_type varchar(30) NOT NULL,
    storage_uri text NOT NULL,
    content_type varchar(100),
    byte_size bigint,
    checksum_sha256 char(64),
    retention_until date,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT report_artifacts_type_check CHECK (
        artifact_type IN (
            'HTML', 'PDF', 'PUBLIC_JSON', 'NORMALIZED_SNAPSHOT',
            'RAW_PAYLOAD', 'METRIC_SERIES'
        )
    ),
    CONSTRAINT report_artifacts_size_check CHECK (
        byte_size IS NULL OR byte_size >= 0
    ),
    CONSTRAINT report_artifacts_run_tenant_fk FOREIGN KEY (
        report_run_id,
        tenant_id
    ) REFERENCES control.report_runs(id, tenant_id),
    UNIQUE (report_run_id, artifact_type, storage_uri)
);

CREATE INDEX IF NOT EXISTS report_artifacts_tenant_idx
ON control.report_artifacts (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS control.collection_errors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_run_id uuid NOT NULL REFERENCES control.report_runs(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE RESTRICT,
    collector varchar(100) NOT NULL,
    stage varchar(100),
    target_type varchar(100),
    target_id varchar(255),
    status_code integer,
    error_code varchar(100),
    message text NOT NULL,
    retryable boolean NOT NULL DEFAULT false,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT collection_errors_run_tenant_fk FOREIGN KEY (
        report_run_id,
        tenant_id
    ) REFERENCES control.report_runs(id, tenant_id)
);

CREATE INDEX IF NOT EXISTS collection_errors_tenant_time_idx
ON control.collection_errors (tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS collection_errors_run_idx
ON control.collection_errors (report_run_id);

CREATE TABLE IF NOT EXISTS control.daily_customer_facts (
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    fact_date date NOT NULL,
    environment varchar(10) NOT NULL,
    latest_report_run_id uuid REFERENCES control.report_runs(id) ON DELETE SET NULL,
    collection_status varchar(30),
    server_count integer NOT NULL DEFAULT 0,
    critical_count integer NOT NULL DEFAULT 0,
    warning_count integer NOT NULL DEFAULT 0,
    info_count integer NOT NULL DEFAULT 0,
    activity_failure_count integer NOT NULL DEFAULT 0,
    collection_error_count integer NOT NULL DEFAULT 0,
    estimated_cost numeric(20, 4),
    confirmed_cost numeric(20, 4),
    cost_confidence varchar(30),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, fact_date),
    CONSTRAINT daily_facts_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT daily_facts_tenant_environment_fk FOREIGN KEY (
        tenant_id,
        environment
    ) REFERENCES control.tenants(id, environment),
    CONSTRAINT daily_facts_counts_check CHECK (
        server_count >= 0
        AND critical_count >= 0
        AND warning_count >= 0
        AND info_count >= 0
        AND activity_failure_count >= 0
        AND collection_error_count >= 0
    ),
    CONSTRAINT daily_facts_cost_confidence_check CHECK (
        cost_confidence IS NULL
        OR cost_confidence IN ('CONFIRMED', 'VERIFIED_ESTIMATE', 'PARTIAL', 'UNAVAILABLE')
    )
);

CREATE INDEX IF NOT EXISTS daily_facts_date_event_idx
ON control.daily_customer_facts (
    fact_date DESC,
    critical_count DESC,
    warning_count DESC
);

CREATE TABLE IF NOT EXISTS control.email_recipients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    email varchar(320) NOT NULL,
    display_name varchar(200),
    receive_daily boolean NOT NULL DEFAULT true,
    receive_monthly boolean NOT NULL DEFAULT true,
    receive_event_alerts boolean NOT NULL DEFAULT false,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE UNIQUE INDEX IF NOT EXISTS email_recipients_tenant_email_uidx
ON control.email_recipients (tenant_id, lower(email));

CREATE TABLE IF NOT EXISTS control.email_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE RESTRICT,
    report_run_id uuid REFERENCES control.report_runs(id) ON DELETE SET NULL,
    recipient_id uuid REFERENCES control.email_recipients(id) ON DELETE SET NULL,
    recipient_email varchar(320) NOT NULL,
    provider varchar(50) NOT NULL,
    provider_message_id varchar(255),
    status varchar(20) NOT NULL DEFAULT 'QUEUED',
    attempt_count integer NOT NULL DEFAULT 0,
    last_error text,
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    sent_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT email_deliveries_status_check CHECK (
        status IN ('QUEUED', 'SENDING', 'SENT', 'FAILED', 'BOUNCED', 'CANCELLED')
    ),
    CONSTRAINT email_deliveries_attempt_check CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS email_deliveries_status_idx
ON control.email_deliveries (status, queued_at)
WHERE status IN ('QUEUED', 'SENDING', 'FAILED');

CREATE TABLE IF NOT EXISTS control.event_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    environment varchar(10) NOT NULL,
    source_type varchar(20) NOT NULL,
    source_event_id varchar(255) NOT NULL,
    occurred_at timestamptz NOT NULL,
    severity varchar(20),
    title text NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'NEW',
    assigned_to uuid REFERENCES control.users(id) ON DELETE SET NULL,
    acknowledged_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    acknowledged_at timestamptz,
    resolved_by uuid REFERENCES control.users(id) ON DELETE SET NULL,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT event_cases_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT event_cases_source_check CHECK (
        source_type IN ('INSIGHT', 'ACTIVITY', 'COLLECTION')
    ),
    CONSTRAINT event_cases_status_check CHECK (
        status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'IGNORED')
    ),
    UNIQUE (tenant_id, source_type, source_event_id)
);

CREATE INDEX IF NOT EXISTS event_cases_open_idx
ON control.event_cases (status, severity, occurred_at DESC)
WHERE status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS');

CREATE TABLE IF NOT EXISTS control.event_case_comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES control.event_cases(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    author_id uuid NOT NULL REFERENCES control.users(id) ON DELETE RESTRICT,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT event_case_comments_body_check CHECK (
        length(btrim(body)) BETWEEN 1 AND 10000
    )
);

CREATE INDEX IF NOT EXISTS event_case_comments_case_idx
ON control.event_case_comments (case_id, created_at);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'tenants',
        'users',
        'memberships',
        'credential_refs',
        'report_schedules',
        'report_runs',
        'email_recipients',
        'email_deliveries',
        'event_cases',
        'event_case_comments'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS set_updated_at ON control.%I',
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER set_updated_at BEFORE UPDATE ON control.%I '
            'FOR EACH ROW EXECUTE FUNCTION control.set_updated_at()',
            table_name
        );
    END LOOP;
END;
$$;

INSERT INTO control.schema_versions (version, description)
VALUES ('020', 'control plane tenant, identity, report and operations tables')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
