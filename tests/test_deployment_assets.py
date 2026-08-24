from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "deploy" / "helm" / "ncp-report"


def test_kubernetes_deployment_assets_exist():
    expected = {
        "Chart.yaml",
        "values.yaml",
        "values-pilot.yaml",
        "values-production.yaml",
        "templates/deployments.yaml",
        "templates/artifact-cleanup-cronjob.yaml",
        "templates/hpa.yaml",
        "templates/ingress.yaml",
        "templates/migration-job.yaml",
        "templates/postgresql.yaml",
        "templates/storage.yaml",
    }

    missing = sorted(path for path in expected if not (CHART / path).is_file())

    assert not missing, f"Missing deployment assets: {missing}"


def test_pilot_storage_is_retained_and_secrets_are_external():
    storage = (CHART / "templates" / "storage.yaml").read_text(encoding="utf-8")
    chart_files = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CHART.rglob("*")
        if path.is_file()
    )

    assert "reclaimPolicy: Retain" in storage
    assert storage.count("helm.sh/resource-policy: keep") == 3
    assert "kind: Secret" not in chart_files
    assert "REPLACE_WITH_RANDOM_VALUE" not in chart_files


def test_database_backups_support_a_replacement_claim_and_are_verified():
    backup = (CHART / "templates" / "backup-cronjob.yaml").read_text(
        encoding="utf-8"
    )
    storage = (CHART / "templates" / "storage.yaml").read_text(
        encoding="utf-8"
    )
    pilot_values = (CHART / "values-pilot.yaml").read_text(encoding="utf-8")

    assert ".Values.backups.existingClaim" in backup
    assert ".Values.backups.createClaim" in storage
    assert "(not .Values.backups.existingClaim)" in storage
    assert 'pg_restore --list "$tmpfile"' in backup
    assert 'mv "$tmpfile" "$finalfile"' in backup
    assert "'ncp-report-*.dump' -mtime +" in backup
    assert "existingClaim: ncp-report-backups-v2" in pilot_values
    assert "createClaim: false" in pilot_values


def test_runtime_and_migration_images_are_separate():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    migration_script = (
        ROOT / "deploy" / "docker" / "migrate.sh"
    ).read_text(encoding="utf-8")

    assert "FROM postgres:16 AS migration" in dockerfile
    assert "FROM python:3.13-slim AS runtime" in dockerfile
    assert "psql -X -v ON_ERROR_STOP=1" in migration_script
    assert "wait_for_schema" in migration_script


def test_worker_roles_can_check_the_required_schema_version():
    migration = (
        ROOT / "database" / "schema" / "100_customer_lifecycle.sql"
    ).read_text(encoding="utf-8")

    assert "GRANT SELECT ON control.schema_versions TO" in migration
    assert "ncp_public_worker" in migration
    assert "ncp_gov_worker" in migration


def test_forced_test_customer_deletion_is_audited():
    migration = (
        ROOT / "database" / "schema" / "110_forced_test_customer_deletion.sql"
    ).read_text(encoding="utf-8")

    assert "forced boolean NOT NULL DEFAULT false" in migration
    assert "OR forced" in migration
    assert "COALESCE(length(btrim(archive_reference)), 0) > 0" in migration


def test_artifact_cleanup_outbox_is_durable_and_msp_only():
    migration = (
        ROOT / "database" / "schema" / "190_artifact_cleanup_outbox.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS control.artifact_cleanup_outbox" in migration
    assert "expected_sha256 char(64) NOT NULL" in migration
    assert "expected_byte_size bigint NOT NULL" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "FOR ALL TO ncp_msp_app" in migration
    assert "REFERENCES control.tenants" not in migration
    assert "VALUES ('190'" in migration


def test_weekly_and_cleanup_migrations_match_schema_wait():
    weekly_migration = (
        ROOT / "database" / "schema" / "200_weekly_reports.sql"
    ).read_text(encoding="utf-8")
    cleanup_migration = (
        ROOT / "database" / "schema" / "210_report_cleanup_queue.sql"
    ).read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS weekly_day smallint" in weekly_migration
    assert "report_type IN ('DAILY', 'WEEKLY', 'MONTHLY')" in weekly_migration
    assert (
        "report_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'CUSTOM')"
        in weekly_migration
    )
    assert "weekly_day BETWEEN 1 AND 7" in weekly_migration
    assert "VALUES ('200'" in weekly_migration
    assert "cleanup_requested_at timestamptz" in cleanup_migration
    assert "cleanup_requested_by uuid" in cleanup_migration
    assert "cleanup_next_attempt_at timestamptz" in cleanup_migration
    assert "report_runs_cleanup_due_idx" in cleanup_migration
    assert "VALUES ('210'" in cleanup_migration
    assert 'schemaVersion: "210"' in (
        CHART / "values.yaml"
    ).read_text(encoding="utf-8")
    assert "waitForSchema: true" in (
        CHART / "values.yaml"
    ).read_text(encoding="utf-8")
    assert 'REPORT_SCHEMA_VERSION:-210' in (
        ROOT / "deploy" / "docker" / "migrate.sh"
    ).read_text(encoding="utf-8")
    deployment_guide = (
        ROOT / "deploy" / "NCP_DEPLOYMENT.md"
    ).read_text(encoding="utf-8")
    assert "schema version `210`" in deployment_guide
    assert "disable every WEEKLY" in deployment_guide
    assert "WEEKLY job is running" in deployment_guide
    assert (
        "must not be rolled back by dropping data or columns"
        in deployment_guide
    )


def test_artifact_cleanup_has_a_scheduled_least_privilege_consumer():
    cleanup = (
        CHART / "templates" / "artifact-cleanup-cronjob.yaml"
    ).read_text(encoding="utf-8")
    cli = (ROOT / "webapp" / "artifact_cleanup.py").read_text(
        encoding="utf-8"
    )

    assert ".Values.artifacts.persistence.enabled" in cleanup
    assert "kind: CronJob" in cleanup
    assert "concurrencyPolicy: Forbid" in cleanup
    assert "webapp.artifact_cleanup" in cleanup
    assert 'value: "msp"' in cleanup
    assert 'value: "ncp_msp_app"' in cleanup
    assert "DB_MSP_APP_PASSWORD" in cleanup
    assert "mountPath: /app/output" in cleanup
    assert "credential-master-key" not in cleanup
    assert "SystemExit(1)" not in cli


def test_compose_artifact_cleanup_is_recurring_and_secret_free():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    cli = (ROOT / "webapp" / "artifact_cleanup.py").read_text(
        encoding="utf-8"
    )
    cleanup = compose.split("\n  artifact-cleanup:\n", 1)[1].split(
        "\n  worker-public:\n", 1
    )[0]

    assert "REPORT_DB_ROLE: msp" in cleanup
    assert "REPORT_DB_USER: ncp_msp_app" in cleanup
    assert "DB_MSP_APP_PASSWORD" in cleanup
    assert "ncp_report_artifacts:/app/output" in cleanup
    assert "--interval-seconds" in cleanup
    assert '- "300"' in cleanup
    assert "CREDENTIAL_MASTER_KEY_FILE" not in cleanup
    assert "WEB_SECRET_KEY" not in cleanup
    assert "\n    secrets:" not in cleanup
    assert 'parser.add_argument("--interval-seconds"' in cli
    assert "time.sleep(args.interval_seconds)" in cli
    for script_name in ("setup_service.ps1", "update_service.ps1"):
        script = (ROOT / script_name).read_text(encoding="utf-8")
        assert "scheduler artifact-cleanup worker-public" in script


def test_period_aware_billing_cost_facts_are_migrated():
    migration = (
        ROOT / "database" / "schema" / "120_billing_cost_facts.sql"
    ).read_text(encoding="utf-8")

    assert "billing_cost_facts" in migration
    assert "PERIOD_ESTIMATE" in migration
    assert "MONTH_END_PROJECTION" in migration
    assert "cloud_account_id" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration


def test_organization_account_billing_is_migrated():
    migration = (
        ROOT / "database" / "schema" / "130_organization_billing.sql"
    ).read_text(encoding="utf-8")

    assert "organization_members" in migration
    assert "billing_account_cost_facts" in migration
    assert "member_no" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration


def test_tenant_report_settings_are_migrated_with_rls():
    migration = (
        ROOT / "database" / "schema" / "140_tenant_report_settings.sql"
    ).read_text(encoding="utf-8")

    assert "control.tenant_report_settings" in migration
    assert "settings jsonb NOT NULL" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "tenant_report_settings_public_worker_access" in migration
    assert "tenant_report_settings_gov_worker_access" in migration
    assert migration.index("ENABLE ROW LEVEL SECURITY") < migration.index(
        "GRANT SELECT ON control.tenant_report_settings"
    )
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" not in migration
    assert "BEGIN;" in migration
    assert "COMMIT;" in migration
    assert "VALUES ('140'" in migration


def test_tenant_branding_is_size_limited_and_tenant_isolated():
    migration = (
        ROOT / "database" / "schema" / "150_tenant_branding.sql"
    ).read_text(encoding="utf-8")

    assert "control.tenant_branding" in migration
    assert "octet_length(logo_content) BETWEEN 1 AND 524288" in migration
    assert "image/svg+xml" not in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "tenant_branding_public_worker_access" in migration
    assert "tenant_branding_gov_worker_access" in migration
    assert "SELECT, INSERT, UPDATE, DELETE" in migration
    assert "VALUES ('150'" in migration
    verification = (
        ROOT / "database" / "verify_database.sql"
    ).read_text(encoding="utf-8")
    assert "tenant_branding" in verification
    assert "Expected at least 37 tables" in verification


def test_report_topology_settings_are_removed_safely():
    migration = (
        ROOT / "database" / "schema" / "160_remove_report_topology_settings.sql"
    ).read_text(encoding="utf-8")

    assert "settings - 'diagram'" in migration
    assert "infrastructure_diagram" in migration
    assert "infrastructure_inventory" in migration
    assert "jsonb_array_elements_text" in migration
    assert "VALUES ('160'" in migration


def test_network_configuration_snapshots_are_separate_and_tenant_isolated():
    migration = (
        ROOT
        / "database"
        / "schema"
        / "170_network_configuration_snapshots.sql"
    ).read_text(encoding="utf-8")

    assert "network_configuration_snapshots" in migration
    assert "cloud_account_id uuid NOT NULL" in migration
    assert "captured_at timestamptz NOT NULL" in migration
    assert "period_start timestamptz NOT NULL" in migration
    assert "period_end timestamptz NOT NULL" in migration
    assert "source varchar(40) NOT NULL" in migration
    assert "schema_version varchar(40) NOT NULL" in migration
    assert "configuration jsonb NOT NULL" in migration
    assert "jsonb_typeof(configuration) = 'array'" in migration
    assert "REFERENCES control.report_runs(id, tenant_id, environment)" in migration
    assert "REFERENCES control.cloud_accounts(id, tenant_id)" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "tenant_id = control.current_tenant_id()" in migration
    assert "environment_worker_access" in migration
    assert "GRANT SELECT, INSERT, DELETE" in migration
    assert "GRANT SELECT, INSERT, UPDATE" not in migration
    assert "VALUES ('170'" in migration


def test_operational_analysis_cases_and_exceptions_are_migrated_safely():
    migration = (
        ROOT / "database" / "schema" / "180_operational_analysis.sql"
    ).read_text(encoding="utf-8")
    verification = (
        ROOT / "database" / "verify_database.sql"
    ).read_text(encoding="utf-8")

    assert "'ANALYSIS'" in migration
    assert "control.policy_exceptions" in migration
    assert "cloud_account_id uuid" in migration
    assert "event_cases_cloud_account_tenant_fk" in migration
    assert "event_cases_tenant_environment_fk" in migration
    assert "event_cases_latest_run_tenant_fk" in migration
    assert "source_type <> 'ANALYSIS'" in migration
    assert "cloud_account_id IS NOT NULL AND report_type IS NOT NULL" in migration
    assert "policy_exceptions_cloud_account_tenant_fk" in migration
    assert "event_cases_analysis_identity_uidx" in migration
    assert "'NOT_DETECTED'" in migration
    assert "report_type varchar(20)" in migration
    assert "event_cases_tenant_id_source_type_source_event_id_key" not in migration
    assert "ON DELETE SET NULL (latest_report_run_id)" in migration
    assert "VALIDATE CONSTRAINT event_cases_analysis_account_check" in migration
    assert "CREATE TABLE IF NOT EXISTS control.daily_account_facts" in migration
    assert "daily_account_facts_cloud_account_tenant_fk" in migration
    assert "daily_account_facts_latest_run_tenant_fk" in migration
    assert "DROP CONSTRAINT IF EXISTS daily_customer_facts_pkey" not in migration
    assert "CREATE OR REPLACE VIEW control.v_msp_customer_daily_status" not in migration
    assert "sum(critical_count)::integer" in (
        ROOT / "database" / "report_repository.py"
    ).read_text(encoding="utf-8")
    assert "policy_exceptions_active_account_idx" in migration
    assert "policy_exceptions_cloud_account_idx" in migration
    assert "expires_at timestamptz NOT NULL" in migration
    assert "approved_by uuid NOT NULL" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "tenant_id = control.current_tenant_id()" in migration
    assert "current_setting('app.environment_scope', true)" in migration
    assert "environment = NULLIF" in migration
    customer_policy = migration.split(
        "CREATE POLICY policy_exceptions_customer_access", 1
    )[1].split("DROP POLICY IF EXISTS policy_exceptions_msp_access", 1)[0]
    assert "FOR SELECT TO ncp_control_app" in customer_policy
    assert "FOR ALL TO ncp_control_app" not in customer_policy
    base_rls = (
        ROOT / "database" / "schema" / "050_security_rls.sql"
    ).read_text(encoding="utf-8")
    assert "IF table_name = 'event_cases'" in base_rls
    event_case_branch = base_rls.split(
        "IF table_name = 'event_cases'", 1
    )[1].split("ELSE", 1)[0]
    assert "tenant_id = control.current_tenant_id()" in event_case_branch
    assert "app.environment_scope" not in event_case_branch
    assert "VALUES ('180'" in migration
    assert "policy_exceptions" in verification
    assert "Event case MSP tenant RLS is missing" in verification
    assert "Policy exception MSP environment RLS is missing" in verification
    assert "Event case tenant boundary constraints are missing" in verification
    assert "Customer role can mutate policy exceptions" in verification
    assert "Daily fact account boundary constraints are missing" in verification
    assert "Expected at least 37 tables" in verification


def test_sourcebuild_deployment_waits_for_migration_job():
    script = (
        ROOT / "deploy" / "scripts" / "deploy-sourcebuild-images.ps1"
    ).read_text(encoding="utf-8")

    assert '"--wait-for-jobs"' in script


def test_sourcebuild_runner_uses_dedicated_credentials_and_exact_build_id():
    script = (
        ROOT / "deploy" / "scripts" / "run-sourcebuild.ps1"
    ).read_text(encoding="utf-8")

    assert "NCP_SOURCEBUILD_ACCESS_KEY" in script
    assert "NCP_SOURCEBUILD_SECRET_KEY" in script
    assert '"x-ncp-apigw-signature-v2"' in script
    assert '"$Method $RequestPath`n$Timestamp`n$AccessKey"' in script
    assert 'RequestPath "/api/v1/project/$ProjectId/build"' in script
    assert 'RequestPath "/api/v1/project/$Id/history"' in script
    assert "Find-SourceBuildHistoryEntry" in script
    assert "Resolve-SourceBuildTag" in script
    assert 'Where-Object { [string]$_.status -eq "success" }' in script
    assert "Sort-Object -Property begin, buildId" in script
    assert "$total - $index" not in script
    assert "failedPhase" in script
    assert "SourceBuild timed out" in script
    assert "SupportsShouldProcess = $true" in script
    assert "NCP_ACCESS_KEY" not in script.replace(
        "NCP_SOURCEBUILD_ACCESS_KEY", ""
    )
    assert "NCP_SECRET_KEY" not in script.replace(
        "NCP_SOURCEBUILD_SECRET_KEY", ""
    )


def test_pilot_uses_private_registry_endpoint_for_cluster_pulls():
    pilot_values = (CHART / "values-pilot.yaml").read_text(encoding="utf-8")

    assert "qoyw4pih.kr.private-ncr.ntruss.com/ncp-report" in pilot_values
    assert "architect-report-build.kr.ncr.ntruss.com" not in pilot_values


def test_registry_secret_script_does_not_accept_secret_as_parameter():
    script = (
        ROOT / "deploy" / "scripts" / "create-registry-secret.ps1"
    ).read_text(encoding="utf-8")

    parameter_block = script.split(")", 1)[0]
    assert "SecretKey" not in parameter_block
    assert "qoyw4pih.kr.private-ncr.ntruss.com" in parameter_block
    assert "Read-Host \"NCP registry Secret Key\" -AsSecureString" in script
    assert '".dockerconfigjson"' in script
    assert "--ignore-not-found -o name" in script


def test_migration_job_and_schema_wait_are_independently_configured():
    deployments = (CHART / "templates" / "deployments.yaml").read_text(
        encoding="utf-8"
    )
    migration = (CHART / "templates" / "migration-job.yaml").read_text(
        encoding="utf-8"
    )
    cleanup = (
        CHART / "templates" / "artifact-cleanup-cronjob.yaml"
    ).read_text(encoding="utf-8")
    hpa = (CHART / "templates" / "hpa.yaml").read_text(encoding="utf-8")

    assert ".Values.migration.waitForSchema" in deployments
    assert ".Values.migration.enabled" not in deployments
    assert ".Values.migration.waitForSchema" in cleanup
    assert ".Values.migration.enabled" not in cleanup
    assert ".Values.migration.enabled" in migration
    assert "autoscaling/v2" in hpa
    assert "HorizontalPodAutoscaler" in hpa
    assert 'if not (and (hasKey $component "autoscaling")' in deployments
    assert "REPORT_OPERATIONAL_ANALYSIS_ENABLED" in deployments
    values = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "operationalAnalysis:" in values
    assert "enabled: true" in values


def test_sourcedeploy_manifest_uses_latest_registry_placeholder():
    manifest = (
        ROOT / "deploy" / "sourcedeploy" / "runtime.yaml"
    ).read_text(encoding="utf-8")

    top_level_deployments = sum(
        line == "kind: Deployment" for line in manifest.splitlines()
    )
    assert top_level_deployments == 4
    assert "kind: HorizontalPodAutoscaler" in manifest
    assert '${registry_endpoint}/ncp-report:latest' in manifest
    assert "kind: Job" not in manifest
    assert manifest.count("name: wait-schema") == 4
    assert '${registry_endpoint}/ncp-report-migrate:latest' in manifest
    assert '"210"' in manifest
    assert "namespace: ncp-report" in manifest


def test_pilot_ingress_uses_small_public_alb():
    pilot_values = (CHART / "values-pilot.yaml").read_text(encoding="utf-8")
    ingress = (CHART / "templates" / "ingress.yaml").read_text(
        encoding="utf-8"
    )

    assert "loadBalancerSize: small" in pilot_values
    assert "networkType: public" in pilot_values
    assert 'subnetId: "315758"' in pilot_values
    assert 'certificateNo: "65260"' in pilot_values
    assert "cookieSecure: true" in pilot_values
    assert "alb.ingress.kubernetes.io/load-balancer-size" in ingress
    assert "helm.sh/resource-policy: keep" in ingress
    assert "alb.ingress.kubernetes.io/idle-timeout" in ingress
    assert "alb.ingress.kubernetes.io/healthcheck-path" in ingress
    assert r'[{\"HTTP\": 80}, {\"HTTPS\": 443}]' in ingress
    assert 'alb.ingress.kubernetes.io/ssl-redirect: "443"' in ingress
    assert "alb.ingress.kubernetes.io/enable-http2" not in ingress
    assert "cookieSecure: true" in (
        CHART / "values-production.yaml"
    ).read_text(encoding="utf-8")


def test_secret_preparation_excludes_global_ncp_credentials():
    script = (
        ROOT / "deploy" / "scripts" / "prepare-kubernetes-secrets.ps1"
    ).read_text(encoding="utf-8")

    assert '"SMTP_PASSWORD"' in script
    assert '$selected["NCP_ACCESS_KEY"]' not in script
    assert '$selected["NCP_SECRET_KEY"]' not in script
    assert "credential-master-key" in script


def test_sourcecommit_release_is_commit_pinned_and_secret_free():
    release = (
        ROOT / "deploy" / "scripts" / "release-from-sourcecommit.ps1"
    ).read_text(encoding="utf-8")
    configure = (
        ROOT / "deploy" / "scripts" / "configure-sourcecommit.ps1"
    ).read_text(encoding="utf-8")

    assert "git status --porcelain" in release
    assert "git push $Remote" in release
    assert "git ls-remote $Remote" in release
    assert '$tag = "git-$shortRevision"' in release
    assert "-Revision $revision" in release
    assert "--atomic --wait" in release
    assert "SecretKey" not in configure
    assert "Password" not in configure


def test_image_build_records_full_git_revision():
    script = (
        ROOT / "deploy" / "scripts" / "build-and-push.ps1"
    ).read_text(encoding="utf-8")

    assert "org.opencontainers.image.revision=$Revision" in script
    assert "Revision must be a full Git commit SHA" in script
    assert "[Parameter(Mandatory = $true)]" in script


def test_sourcebuild_has_separate_runtime_and_migration_images():
    runtime = (ROOT / "Dockerfile.runtime").read_text(encoding="utf-8")
    migration = (ROOT / "Dockerfile.migration").read_text(encoding="utf-8")

    assert "webapp.wsgi:app" in runtime
    assert "postgres:16" not in runtime
    assert "FROM postgres:16" in migration
    assert "database/schema" in migration


def test_web_receives_deployed_image_tag_and_source_revision():
    deployments = (
        CHART / "templates" / "deployments.yaml"
    ).read_text(encoding="utf-8")

    assert "APP_VERSION" in deployments
    assert "$root.Values.image.tag" in deployments
    assert "APP_SOURCE_REVISION" in deployments
    assert "$root.Values.sourceRevision" in deployments


def test_sourcebuild_test_dependencies_are_separate_from_runtime():
    runtime_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    build_requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    setup = (ROOT / "deploy" / "SOURCEBUILD_SETUP.md").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "pytest" not in runtime_requirements.lower()
    assert "-r requirements.txt" in build_requirements
    assert "pytest" in build_requirements.lower()
    assert "requirements-dev.txt" in setup
    assert "tests/" in dockerignore.splitlines()
    assert "deploy/private/" in dockerignore.splitlines()


def test_normal_release_does_not_build_images_locally():
    legacy = (
        ROOT / "deploy" / "scripts" / "release-from-sourcecommit.ps1"
    ).read_text(encoding="utf-8")
    deployment = (
        ROOT / "deploy" / "scripts" / "deploy-sourcebuild-images.ps1"
    ).read_text(encoding="utf-8")

    assert "AllowLocalBuild" in legacy
    assert "Local image builds are disabled" in legacy
    assert "docker build" not in deployment.lower()
    assert "git ls-remote sourcecommit refs/heads/master" in deployment
    assert '"--atomic", "--wait"' in deployment
    assert '[Parameter(Mandatory = $true)]\n    [string]$MigrationTag' in deployment
    assert '"migration.image.tag=$MigrationTag"' in deployment
    assert "if ($EnableMigration)" not in deployment
