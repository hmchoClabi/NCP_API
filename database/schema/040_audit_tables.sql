\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS audit.access_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid REFERENCES control.tenants(id) ON DELETE SET NULL,
    actor_id uuid REFERENCES control.users(id) ON DELETE SET NULL,
    actor_type varchar(30) NOT NULL,
    action varchar(100) NOT NULL,
    resource_type varchar(100),
    resource_id varchar(255),
    result varchar(20) NOT NULL,
    source_ip inet,
    user_agent text,
    request_id varchar(100),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT access_logs_actor_type_check CHECK (
        actor_type IN ('CUSTOMER_USER', 'MSP_USER', 'WORKER', 'SYSTEM')
    ),
    CONSTRAINT access_logs_result_check CHECK (
        result IN ('SUCCESS', 'DENIED', 'FAILED')
    ),
    CONSTRAINT access_logs_details_object_check CHECK (
        jsonb_typeof(details) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS access_logs_tenant_time_idx
ON audit.access_logs (tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS access_logs_actor_time_idx
ON audit.access_logs (actor_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS access_logs_action_time_idx
ON audit.access_logs (action, occurred_at DESC);

CREATE TABLE IF NOT EXISTS audit.authentication_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid REFERENCES control.users(id) ON DELETE SET NULL,
    email_attempted varchar(320),
    event_type varchar(40) NOT NULL,
    result varchar(20) NOT NULL,
    source_ip inet,
    user_agent text,
    failure_reason varchar(255),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT authentication_logs_event_check CHECK (
        event_type IN (
            'LOGIN', 'LOGOUT', 'MFA_CHALLENGE', 'PASSWORD_RESET',
            'ACCOUNT_LOCK', 'SESSION_REVOKE'
        )
    ),
    CONSTRAINT authentication_logs_result_check CHECK (
        result IN ('SUCCESS', 'DENIED', 'FAILED')
    )
);

CREATE INDEX IF NOT EXISTS authentication_logs_user_time_idx
ON audit.authentication_logs (user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS authentication_logs_ip_time_idx
ON audit.authentication_logs (source_ip, occurred_at DESC);

CREATE TABLE IF NOT EXISTS audit.credential_access_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE RESTRICT,
    credential_ref_id uuid REFERENCES control.credential_refs(id) ON DELETE SET NULL,
    worker_role varchar(80) NOT NULL,
    purpose varchar(100) NOT NULL,
    result varchar(20) NOT NULL,
    report_run_id uuid REFERENCES control.report_runs(id) ON DELETE SET NULL,
    error_code varchar(100),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT credential_access_logs_result_check CHECK (
        result IN ('SUCCESS', 'DENIED', 'FAILED')
    )
);

CREATE INDEX IF NOT EXISTS credential_access_logs_tenant_time_idx
ON audit.credential_access_logs (tenant_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS audit.data_change_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid REFERENCES control.tenants(id) ON DELETE SET NULL,
    actor_id uuid REFERENCES control.users(id) ON DELETE SET NULL,
    table_name varchar(150) NOT NULL,
    record_id varchar(255),
    operation varchar(10) NOT NULL,
    changed_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    request_id varchar(100),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT data_change_logs_operation_check CHECK (
        operation IN ('INSERT', 'UPDATE', 'DELETE')
    ),
    CONSTRAINT data_change_logs_fields_object_check CHECK (
        jsonb_typeof(changed_fields) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS data_change_logs_tenant_time_idx
ON audit.data_change_logs (tenant_id, occurred_at DESC);

INSERT INTO control.schema_versions (version, description)
VALUES ('040', 'append-oriented access, authentication and credential audit tables')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
