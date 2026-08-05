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
    assert "kind: Secret" not in chart_files
    assert "REPLACE_WITH_RANDOM_VALUE" not in chart_files


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


def test_pilot_uses_private_registry_for_cluster_pulls():
    pilot_values = (CHART / "values-pilot.yaml").read_text(encoding="utf-8")

    assert "hhgee3ff.kr.private-ncr.ntruss.com/ncp-report" in pilot_values
    assert "architect-ncp-report.kr.ncr.ntruss.com/ncp-report" not in pilot_values


def test_registry_secret_script_does_not_accept_secret_as_parameter():
    script = (
        ROOT / "deploy" / "scripts" / "create-registry-secret.ps1"
    ).read_text(encoding="utf-8")

    parameter_block = script.split(")", 1)[0]
    assert "SecretKey" not in parameter_block
    assert "Read-Host \"NCP registry Secret Key\" -AsSecureString" in script
    assert '".dockerconfigjson"' in script
    assert "--ignore-not-found -o name" in script


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
