param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeTag,
    [Parameter(Mandatory = $true)]
    [string]$MigrationTag,
    [Parameter(Mandatory = $true)]
    [string]$SourceRevision,
    [string]$Namespace = "ncp-report",
    [string]$Release = "ncp-report",
    [string]$ValuesFile = ".\deploy\helm\ncp-report\values-pilot.yaml",
    [string]$Helm = "helm"
)

$ErrorActionPreference = "Stop"

foreach ($tag in @($RuntimeTag, $MigrationTag)) {
    if ($tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$') {
        throw "SourceBuild image tag is invalid."
    }
}
if ($SourceRevision -notmatch '^[0-9a-f]{40}$') {
    throw "SourceRevision must be a full lowercase Git commit SHA."
}
if (-not (Test-Path -LiteralPath $ValuesFile)) {
    throw "Values file not found."
}

$remoteLine = git ls-remote sourcecommit refs/heads/main
if ($LASTEXITCODE -ne 0 -or -not $remoteLine) {
    throw "Unable to verify SourceCommit main."
}
$remoteRevision = ($remoteLine -split '\s+')[0].ToLowerInvariant()
if ($remoteRevision -ne $SourceRevision) {
    throw "Requested revision does not match SourceCommit main."
}

& $Helm upgrade --install $Release .\deploy\helm\ncp-report `
    --namespace $Namespace --create-namespace `
    -f $ValuesFile `
    --set-string "image.tag=$RuntimeTag" `
    --set-string "migration.image.tag=$MigrationTag" `
    --set-string "sourceRevision=$SourceRevision" `
    --atomic --wait --timeout 10m
if ($LASTEXITCODE -ne 0) { throw "Helm deployment failed." }

Write-Host "Deployed SourceBuild images for SourceCommit $SourceRevision."
