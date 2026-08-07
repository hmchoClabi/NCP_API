param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeTag,
    [Parameter(Mandatory = $true)]
    [string]$SourceRevision,
    [string]$MigrationTag = "",
    [switch]$EnableMigration,
    [string]$RuntimeRepository =
        "qoyw4pih.kr.private-ncr.ntruss.com/ncp-report",
    [string]$MigrationRepository =
        "qoyw4pih.kr.private-ncr.ntruss.com/ncp-report-migrate",
    [string]$Namespace = "ncp-report",
    [string]$Release = "ncp-report",
    [string]$ValuesFile = ".\deploy\helm\ncp-report\values-pilot.yaml",
    [string]$Helm = "helm"
)

$ErrorActionPreference = "Stop"

foreach ($tag in @($RuntimeTag, $MigrationTag) | Where-Object { $_ }) {
    if ($tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$') {
        throw "SourceBuild image tag is invalid."
    }
}
if ($EnableMigration -and [string]::IsNullOrWhiteSpace($MigrationTag)) {
    throw "MigrationTag is required when EnableMigration is set."
}
foreach ($repository in @($RuntimeRepository, $MigrationRepository)) {
    if ($repository -notmatch '^[a-z0-9.-]+/[a-z0-9._-]+$') {
        throw "Container image repository is invalid."
    }
}
if ($SourceRevision -notmatch '^[0-9a-f]{40}$') {
    throw "SourceRevision must be a full lowercase Git commit SHA."
}
if (-not (Test-Path -LiteralPath $ValuesFile)) {
    throw "Values file not found."
}

$remoteLine = git ls-remote sourcecommit refs/heads/master
if ($LASTEXITCODE -ne 0 -or -not $remoteLine) {
    throw "Unable to verify SourceCommit master."
}
$remoteRevision = ($remoteLine -split '\s+')[0].ToLowerInvariant()
if ($remoteRevision -ne $SourceRevision) {
    throw "Requested revision does not match SourceCommit master."
}

$helmArguments = @(
    "upgrade", "--install", $Release, ".\deploy\helm\ncp-report",
    "--namespace", $Namespace, "--create-namespace",
    "-f", $ValuesFile,
    "--set-string", "image.repository=$RuntimeRepository",
    "--set-string", "image.tag=$RuntimeTag",
    "--set-string", "sourceRevision=$SourceRevision",
    "--set", "migration.enabled=$($EnableMigration.IsPresent.ToString().ToLowerInvariant())",
    "--atomic", "--wait", "--wait-for-jobs", "--timeout", "10m"
)
if ($EnableMigration) {
    $helmArguments += @(
        "--set-string", "migration.image.repository=$MigrationRepository",
        "--set-string", "migration.image.tag=$MigrationTag"
    )
}

& $Helm @helmArguments
if ($LASTEXITCODE -ne 0) { throw "Helm deployment failed." }

Write-Host "Deployed SourceBuild images for SourceCommit $SourceRevision."
