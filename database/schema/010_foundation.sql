\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS control AUTHORIZATION ncp_schema_owner;
CREATE SCHEMA IF NOT EXISTS public_data AUTHORIZATION ncp_schema_owner;
CREATE SCHEMA IF NOT EXISTS gov_data AUTHORIZATION ncp_schema_owner;
CREATE SCHEMA IF NOT EXISTS audit AUTHORIZATION ncp_schema_owner;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA control, public_data, gov_data, audit FROM PUBLIC;

CREATE OR REPLACE FUNCTION control.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION control.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION control.current_actor_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('app.actor_id', true), '')::uuid
$$;

CREATE TABLE IF NOT EXISTS control.schema_versions (
    version varchar(40) PRIMARY KEY,
    description text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO control.schema_versions (version, description)
VALUES ('010', 'schemas, extensions and common functions')
ON CONFLICT (version) DO UPDATE
SET description = EXCLUDED.description;
