\set ON_ERROR_STOP on
\getenv control_app_password DB_CONTROL_APP_PASSWORD
\getenv public_worker_password DB_PUBLIC_WORKER_PASSWORD
\getenv gov_worker_password DB_GOV_WORKER_PASSWORD
\getenv msp_app_password DB_MSP_APP_PASSWORD

SELECT 'CREATE ROLE ncp_schema_owner NOLOGIN'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'ncp_schema_owner'
) \gexec

SELECT 'CREATE ROLE ncp_control_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'ncp_control_app'
) \gexec

SELECT 'CREATE ROLE ncp_public_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'ncp_public_worker'
) \gexec

SELECT 'CREATE ROLE ncp_gov_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'ncp_gov_worker'
) \gexec

SELECT 'CREATE ROLE ncp_msp_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'ncp_msp_app'
) \gexec

ALTER ROLE ncp_control_app PASSWORD :'control_app_password';
ALTER ROLE ncp_public_worker PASSWORD :'public_worker_password';
ALTER ROLE ncp_gov_worker PASSWORD :'gov_worker_password';
ALTER ROLE ncp_msp_app PASSWORD :'msp_app_password';

ALTER ROLE ncp_control_app SET timezone = 'UTC';
ALTER ROLE ncp_public_worker SET timezone = 'UTC';
ALTER ROLE ncp_gov_worker SET timezone = 'UTC';
ALTER ROLE ncp_msp_app SET timezone = 'UTC';

REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO
    ncp_control_app,
    ncp_public_worker,
    ncp_gov_worker,
    ncp_msp_app;
