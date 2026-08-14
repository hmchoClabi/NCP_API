# NCP report service database

The local database uses one PostgreSQL instance and one `ncp_report` database.
Logical separation is provided by schemas and database roles.

```text
ncp_report
├── control       shared tenant, identity, scheduling and report metadata
├── public_data   private-cloud customer report details
├── gov_data      government-cloud customer report details
└── audit         append-oriented security and access history
```

## One-click setup on Windows

Docker Desktop must be running. Double-click `setup_database.cmd`, or run:

```powershell
.\setup_database.cmd
```

The CMD wrapper applies a process-local PowerShell execution-policy bypass so
it also works on machines where unsigned `.ps1` execution is disabled. It does
not change the system execution policy.

The script performs the following operations safely and idempotently:

1. Creates `.env.db` with random local passwords when it does not exist.
2. Starts the PostgreSQL container.
3. Waits for the database health check.
4. Applies every SQL file under `database/schema` in filename order.
5. Verifies schemas, tables, RLS and database roles.

Re-running the script does not delete data. There is intentionally no automatic
reset option. To inspect connection settings, open the Git-ignored `.env.db`.

## Data placement

PostgreSQL stores searchable and transactional data:

- tenants, users, memberships and platform roles;
- credential references (never NCP access or secret keys in plaintext);
- schedules, report executions, artifacts and collection errors;
- reproducible normalized report snapshots and separate network configuration
  snapshots captured when a report is generated;
- Insight and Activity events, metric summaries and cost details;
- daily MSP dashboard facts, email delivery and audit history.
- deterministic operational findings, action ownership and expiring policy
  exceptions.

Large HTML/PDF files, raw API payloads and long metric series should move to
Object Storage in production. Their URI, checksum and metadata stay in the DB.

## Table catalog

### `control` schema

| Table | Purpose |
| --- | --- |
| `tenants` | Customer identity, Public/GOV environment and region |
| `tenant_report_settings` | Per-customer report sections and resource options |
| `tenant_branding` | Validated customer logo used by newly generated report snapshots |
| `users` | Login identity and MFA state; passwords are hashes only |
| `memberships` | Customer-scoped viewer/admin roles |
| `platform_roles` | MSP and system-wide roles with environment scope |
| `credential_refs` | KMS, environment or Docker Secret references only |
| `report_schedules` | Daily, monthly and custom report schedules |
| `report_runs` | Idempotent collection/render execution state |
| `report_artifacts` | HTML, PDF, JSON and Object Storage metadata |
| `collection_errors` | Collector-stage errors and retry classification |
| `daily_customer_facts` | Fast MSP daily dashboard aggregates |
| `email_recipients` | Tenant report and event recipient preferences |
| `email_deliveries` | Delivery attempts, provider IDs and failures |
| `event_cases` | Collection/event case storage plus dormant ANALYSIS action history; new ANALYSIS case creation is disabled |
| `event_case_comments` | Operations comments attached to a case |
| `policy_exceptions` | Dormant legacy exceptions retained without application read/write paths |
| `customer_deletion_tombstones` | Hashed customer-code deletion ledger, archive reference and forced-test-deletion flag |
| `schema_versions` | Applied baseline schema components |

### Environment data schemas

`public_data` and `gov_data` contain the same environment-scoped tables. A constant
environment check and a composite foreign key prevent a report run from being
written to the wrong schema.

| Table | Purpose |
| --- | --- |
| `report_snapshots` | Versioned normalized JSON used to reproduce a report |
| `network_configuration_snapshots` | Route Table, ACG and Network ACL configuration captured at report generation time |
| `insight_events` | Searchable Cloud Insight events and rule conditions |
| `activity_events` | Searchable account, action and resource audit events |
| `metric_series` | Chart points or an external artifact URI |
| `metric_summaries` | Minimum, average and maximum metric values |
| `cost_details` | Confirmed/estimated costs and calculation confidence |
| `billing_cost_facts` | Period-aware confirmed, estimated and projected billing totals |
| `raw_payload_refs` | URI and checksum for raw collector payloads |

`network_configuration_snapshots.captured_at` is the time the report-generation
workflow captured the network configuration. `period_start` and `period_end`
are the report's requested data range and are kept separately; they do not mean
that NCP returned a historical configuration for that range. A snapshot can be
reused as historical evidence only when its `captured_at` falls inside the
requested report period. Reopening or viewing a report does not create a new
snapshot, and a reused snapshot is never saved again with a newer timestamp.

### `audit` schema

| Table | Purpose |
| --- | --- |
| `access_logs` | Data views, downloads and API access outcomes |
| `authentication_logs` | Login, MFA, lock and session events |
| `credential_access_logs` | Worker credential-decryption audit trail |
| `data_change_logs` | Security-relevant configuration changes |

Application roles normally receive insert-only permission on audit tables.
The MSP role has column-level update permission only for personal fields that
must be redacted during irreversible anonymization; it cannot delete audit
history or alter event identity, action, result, or timestamps.

## Customer lifecycle

Customer removal is deliberately split into explicit stages:

1. **Offboard** disables accounts, removes encrypted credentials, memberships,
   schedules and recipients, while preserving reports and audit history.
2. **Reactivate** returns an offboarded customer to `ACTIVE`. API credentials
   and customer memberships are never restored automatically and must be
   registered again.
3. **Anonymize** irreversibly replaces customer, orphan-user, account and
   report-snapshot identifiers while retaining report and audit history.
4. **Permanently delete** removes the tenant and reports. Reports require an
   external archive reference; only a SHA-256 customer-code tombstone, counts,
   environment, actor and deletion time remain.

The web workflow requires the exact customer code and an explicit confirmation
phrase for anonymization and permanent deletion. A running report job blocks
all destructive lifecycle operations.

## Integrated views

- `control.v_msp_customer_daily_status`: all-customer Public/GOV dashboard;
- `control.v_report_run_status`: report queue and execution status;
- `control.v_all_insight_events`: unified environment event feed;
- `control.v_event_customer_daily`: daily event counts per customer.

## Roles

| Role | Intended use |
| --- | --- |
| `ncp_control_app` | Customer-facing API with tenant context |
| `ncp_public_worker` | Public NCP collection worker |
| `ncp_gov_worker` | GOV NCP collection worker |
| `ncp_msp_app` | MSP control plane and cross-customer views |
| `ncp_schema_owner` | Non-login schema ownership marker |

Before a customer-scoped connection queries tenant data, set the tenant context
inside the transaction:

```sql
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000000';
```

RLS denies tenant-scoped access when this value is missing. Worker access is
also restricted to tenants matching its `public` or `gov` environment.

The application no longer creates ANALYSIS action cases or reads and writes
policy exceptions. These rows and schema objects remain intact so a runtime
rollback does not lose audit history. Physical deletion requires a separately
approved destructive migration. Hidden legacy policy selections are likewise
preserved when report settings are saved, but the current runtime ignores them.

MSP access to dormant policy exceptions still requires an environment context
in the same transaction:

```sql
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000000';
SET LOCAL app.environment_scope = 'public'; -- or 'gov'
```

`control.event_cases` remains tenant-scoped and its composite foreign keys
prevent cross-environment references. `control.policy_exceptions` denies the
MSP role when either setting is absent or when the tenant environment does not
match.

Residual hardening scope: older MSP policies on other control/data tables still
allow broader database-level reads and currently rely on application route
authorization for environment separation. Extending the environment predicate
to every legacy MSP policy, or using separate Public/GOV MSP database roles,
requires a dedicated compatibility migration and remains follow-up work.

## Cloud migration

Pin the local PostgreSQL major version to the future managed database version.
In production use TLS, separate migration credentials, a connection pool, KMS
or a secret manager, automated backups, and environment-specific storage.

The application uses standard PostgreSQL settings and has no Docker-specific
database code. Local development reads `.env.db`; NKS should inject a
`REPORT_DATABASE_URL` Kubernetes Secret that points to the Cloud DB for
PostgreSQL private endpoint. Set `REPORT_DB_SSLMODE=require` (or
`verify-full` with the managed CA), keep the database outside public networks,
and allow port 5432 only from the NKS worker or pod network.

Use separate Secrets and deployments for `msp`, `public_worker`, and
`gov_worker`. The CLI currently defaults to the MSP role because it onboards a
customer record on first use. Scheduled workers should use the environment
worker role plus `REPORT_DB_TENANT_ID`; the web application should use the
control role and set tenant context per transaction. Run schema migration as a
separate NKS Job using a migration credential, never from every application
pod. Add PgBouncer or an application connection pool before increasing pod
replicas substantially.
