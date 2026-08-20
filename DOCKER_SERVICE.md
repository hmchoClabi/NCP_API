# NCP Report Hub local Docker service

This package runs the PostgreSQL-backed report portal locally without
Kubernetes. The image is stateless so the same image can later run in NKS.

## Included

- MSP and customer login with server-side sessions;
- MSP issue dashboard and Public/GOV customer menus;
- customer-scoped report history and stored snapshot views;
- multiple NCP accounts per customer;
- MSP-admin-only customer and API credential registration;
- AES-256-GCM envelope encryption using a Docker-mounted master key;
- immediate daily/monthly generation from MSP and customer screens;
- per-account daily/monthly schedules backed by a durable PostgreSQL queue;
- isolated Public and GOV report workers;
- five-minute durable local artifact cleanup retries;
- PostgreSQL migration container and health checks;
- one-command image rebuild and container replacement.

## First startup

Docker Desktop must be running. Execute:

```powershell
.\setup_service.ps1
```

Or double-click `setup_service.cmd`. Setup creates Git-ignored settings and a
256-bit credential master key, builds the image, applies DB migrations, and
starts the portal at <http://127.0.0.1:8080>.

Create the first MSP administrator. The password is entered interactively and
is never placed in the command line:

```powershell
.\setup_admin.ps1 -Email admin@example.com -DisplayName "MSP 관리자"
```

Log in, choose Public or GOV customers, create a customer, then open its detail
page to register one or more NCP accounts. Keys are encrypted before the DB
transaction completes and are never displayed again.

Create a customer login after the customer exists:

```powershell
.\setup_customer_user.ps1 `
  -Email viewer@example.com `
  -DisplayName "고객 담당자" `
  -TenantCode customer-001
```

A customer user can see every NCP account and report belonging to memberships
assigned to that login, but cannot open another tenant's report URL.

## Generate a report from a stored account

Run the account UUID through the tools profile:

```powershell
docker compose -p ncp-report `
  --env-file .env.db --env-file .env.service `
  --profile tools run --rm report-runner `
  python -m webapp.worker `
  --account-id ACCOUNT_UUID --target-day today
```

The Worker decrypts credentials only in memory, runs the existing pipeline,
writes normalized data to PostgreSQL and stores HTML/JSON in the artifact
volume.

## Immediate and scheduled generation

Open a customer or customer portal page and choose an NCP account. All users
who can view that customer can request an immediate daily or monthly report.
`MSP_ADMIN` and `CUSTOMER_ADMIN` users can also register execution times:

- daily schedules create the previous day's report;
- monthly schedules create the previous month's report on days 1 through 28;
- all schedule inputs and displayed next-run times use Asia/Seoul time.

The scheduler checks due entries every 30 seconds. Public and GOV workers claim
only jobs for their own environment and retry failures up to three times. Their
state survives container restarts because it is held in PostgreSQL. Check them
with:

```powershell
docker compose -p ncp-report `
  --env-file .env.db --env-file .env.service `
  logs --tail 100 scheduler artifact-cleanup worker-public worker-gov
```

The `artifact-cleanup` service uses the MSP database role and artifact volume
to retry durable cleanup rows every five minutes. It does not mount the NCP
credential master key. Run a one-time retry with
`python -m webapp.artifact_cleanup --limit 100` inside the web container.

The immediate-generation panel also accepts a KST start and end time. Custom
time ranges must remain inside one calendar month because the existing billing
collector uses a monthly billing API. Each manual or scheduled execution now
creates its own immutable report snapshot. Open **생성 이력** to see the account,
request time, report period, trigger type, result, and a link that reproduces
that exact snapshot without calling NCP again. MSP users can review and pause
all customer schedules from **전체 실행 일정**.

## Hourly customer status dashboard

Do not call NCP synchronously when a customer page opens. A single account can
require multiple Server and Cloud Insight calls; across hundreds of customers
this makes page latency and availability depend directly on NCP APIs.

The recommended production flow is a separate hourly status collector:

1. enqueue one lightweight job per active account every hour;
2. collect only the latest one-hour server metrics and Insight incidents;
3. skip Billing and full report rendering;
4. store a compact account-health snapshot with observation time and errors;
5. render the newest snapshot immediately and show its freshness on the page.

Keep this queue separate from daily/monthly report jobs so a large report batch
cannot delay operational status. On-demand refresh can later enqueue the same
lightweight job asynchronously instead of blocking the HTTP request.

For higher local throughput, add worker replicas without changing code:

```powershell
docker compose -p ncp-report `
  --env-file .env.db --env-file .env.service `
  up -d --scale worker-public=3 --scale worker-gov=2
```

Use the same horizontal scaling model after moving to NKS. The queue uses row
locking so each job is claimed by only one worker. If a worker disappears while
processing, its lease is recovered after six hours and the job is retried.

## Update after changing code

```powershell
.\update_service.ps1
```

If local PowerShell script execution is restricted, double-click
`update_service.cmd` instead. It uses a process-local policy bypass and does
not change the system execution policy.

This creates a timestamped image tag, builds it, runs idempotent migrations,
and replaces the web, scheduler, cleanup, and worker containers. Inspect status
and logs with:

```powershell
docker compose -p ncp-report `
  --env-file .env.db --env-file .env.service ps

docker compose -p ncp-report `
  --env-file .env.db --env-file .env.service logs --tail 100 web
```

## Security boundaries

- `.env.db`, `.env.service`, and `secrets/` are Git-ignored.
- The master key is mounted as a file, never an environment value.
- Only MSP administrators can submit credential registration forms.
- API keys are never returned by repository or web read methods.
- Customer report access is checked server-side using membership tenant IDs.
- Rotate credentials previously stored in customer PowerShell scripts.

For shared or production use, enable HTTPS and set `WEB_COOKIE_SECURE=true`.
Before NKS migration, split web, Public Worker, and GOV Worker DB roles and
replace `LocalKeyEncryptionProvider` with an NCP KMS implementation of the same
interface.
