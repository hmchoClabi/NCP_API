\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.cloud_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    account_code varchar(80) NOT NULL,
    display_name varchar(200) NOT NULL,
    environment varchar(10) NOT NULL,
    region varchar(20) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT cloud_accounts_code_format CHECK (
        account_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
    ),
    CONSTRAINT cloud_accounts_environment_check CHECK (
        environment IN ('public', 'gov')
    ),
    CONSTRAINT cloud_accounts_status_check CHECK (
        status IN ('ACTIVE', 'DISABLED', 'CREDENTIAL_ERROR')
    ),
    CONSTRAINT cloud_accounts_tenant_environment_fk FOREIGN KEY (
        tenant_id, environment
    ) REFERENCES control.tenants(id, environment),
    UNIQUE (tenant_id, account_code),
    UNIQUE (id, tenant_id)
);

CREATE TABLE IF NOT EXISTS control.encrypted_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES control.tenants(id) ON DELETE CASCADE,
    cloud_account_id uuid NOT NULL UNIQUE,
    provider varchar(30) NOT NULL DEFAULT 'LOCAL_ENVELOPE',
    key_reference text NOT NULL,
    algorithm varchar(30) NOT NULL DEFAULT 'AES-256-GCM',
    encrypted_dek bytea NOT NULL,
    dek_nonce bytea NOT NULL,
    ciphertext bytea NOT NULL,
    credential_nonce bytea NOT NULL,
    access_key_hint varchar(16),
    credential_version integer NOT NULL DEFAULT 1,
    status varchar(20) NOT NULL DEFAULT 'VALID',
    last_verified_at timestamptz,
    rotated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT encrypted_credentials_account_fk FOREIGN KEY (
        cloud_account_id, tenant_id
    ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT encrypted_credentials_provider_check CHECK (
        provider IN ('LOCAL_ENVELOPE', 'NCP_KMS')
    ),
    CONSTRAINT encrypted_credentials_algorithm_check CHECK (
        algorithm = 'AES-256-GCM'
    ),
    CONSTRAINT encrypted_credentials_status_check CHECK (
        status IN ('VALID', 'INVALID', 'DISABLED', 'ROTATION_REQUIRED')
    ),
    CONSTRAINT encrypted_credentials_version_check CHECK (
        credential_version > 0
    )
);

CREATE TABLE IF NOT EXISTS control.user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES control.users(id) ON DELETE CASCADE,
    token_hash char(64) NOT NULL UNIQUE,
    csrf_token_hash char(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT user_sessions_expiry_check CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS user_sessions_user_idx
ON control.user_sessions (user_id, expires_at DESC);

ALTER TABLE control.report_runs
ADD COLUMN IF NOT EXISTS cloud_account_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'report_runs_cloud_account_fk'
    ) THEN
        ALTER TABLE control.report_runs
        ADD CONSTRAINT report_runs_cloud_account_fk FOREIGN KEY (
            cloud_account_id, tenant_id
        ) REFERENCES control.cloud_accounts(id, tenant_id) ON DELETE RESTRICT;
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS set_updated_at ON control.cloud_accounts;
CREATE TRIGGER set_updated_at BEFORE UPDATE ON control.cloud_accounts
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();
DROP TRIGGER IF EXISTS set_updated_at ON control.encrypted_credentials;
CREATE TRIGGER set_updated_at BEFORE UPDATE ON control.encrypted_credentials
FOR EACH ROW EXECUTE FUNCTION control.set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON
    control.cloud_accounts,
    control.encrypted_credentials,
    control.user_sessions
TO ncp_msp_app;

GRANT SELECT ON control.cloud_accounts TO
    ncp_control_app, ncp_public_worker, ncp_gov_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON control.user_sessions TO ncp_control_app;
GRANT SELECT ON control.encrypted_credentials TO
    ncp_public_worker, ncp_gov_worker;

ALTER TABLE control.cloud_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.cloud_accounts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cloud_accounts_msp_access ON control.cloud_accounts;
CREATE POLICY cloud_accounts_msp_access ON control.cloud_accounts
FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS cloud_accounts_customer_access ON control.cloud_accounts;
CREATE POLICY cloud_accounts_customer_access ON control.cloud_accounts
FOR SELECT TO ncp_control_app
USING (tenant_id = control.current_tenant_id());
DROP POLICY IF EXISTS cloud_accounts_public_worker_access ON control.cloud_accounts;
CREATE POLICY cloud_accounts_public_worker_access ON control.cloud_accounts
FOR SELECT TO ncp_public_worker USING (environment = 'public');
DROP POLICY IF EXISTS cloud_accounts_gov_worker_access ON control.cloud_accounts;
CREATE POLICY cloud_accounts_gov_worker_access ON control.cloud_accounts
FOR SELECT TO ncp_gov_worker USING (environment = 'gov');

ALTER TABLE control.encrypted_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.encrypted_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS encrypted_credentials_msp_access ON control.encrypted_credentials;
CREATE POLICY encrypted_credentials_msp_access ON control.encrypted_credentials
FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS encrypted_credentials_public_worker_access ON control.encrypted_credentials;
CREATE POLICY encrypted_credentials_public_worker_access ON control.encrypted_credentials
FOR SELECT TO ncp_public_worker USING (
    EXISTS (
        SELECT 1 FROM control.cloud_accounts account
        WHERE account.id = cloud_account_id AND account.environment = 'public'
    )
);
DROP POLICY IF EXISTS encrypted_credentials_gov_worker_access ON control.encrypted_credentials;
CREATE POLICY encrypted_credentials_gov_worker_access ON control.encrypted_credentials
FOR SELECT TO ncp_gov_worker USING (
    EXISTS (
        SELECT 1 FROM control.cloud_accounts account
        WHERE account.id = cloud_account_id AND account.environment = 'gov'
    )
);

ALTER TABLE control.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.user_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_sessions_msp_access ON control.user_sessions;
CREATE POLICY user_sessions_msp_access ON control.user_sessions
FOR ALL TO ncp_msp_app USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS user_sessions_control_access ON control.user_sessions;
CREATE POLICY user_sessions_control_access ON control.user_sessions
FOR ALL TO ncp_control_app
USING (
    user_id IN (
        SELECT membership.user_id
        FROM control.memberships membership
        WHERE membership.tenant_id = control.current_tenant_id()
    )
)
WITH CHECK (
    user_id IN (
        SELECT membership.user_id
        FROM control.memberships membership
        WHERE membership.tenant_id = control.current_tenant_id()
    )
);

INSERT INTO control.schema_versions (version, description)
VALUES ('070', 'web portal, multi-account credentials and sessions')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
