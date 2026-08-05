param(
    [string]$Registry = "architect-ncp-report.kr.ncr.ntruss.com",
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$Context = ".",
    [string]$Revision = ""
)

$ErrorActionPreference = "Stop"

if ($Registry -notmatch '^[a-z0-9.-]+\.ncr\.ntruss\.com$') {
    throw "Registry must be an NCP Container Registry public endpoint."
}
if ($Tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') {
    throw "Tag is not a valid container image tag."
}
$resolvedContext = (Resolve-Path -LiteralPath $Context).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedContext "Dockerfile"))) {
    throw "Build context must contain Dockerfile."
}
if ($Revision -and $Revision -notmatch '^[0-9a-f]{40}$') {
    throw "Revision must be a full Git commit SHA."
}

$runtimeImage = "$Registry/ncp-report:$Tag"
$migrationImage = "$Registry/ncp-report-migrate:$Tag"
$labelArguments = @()
if ($Revision) {
    $labelArguments = @(
        "--label", "org.opencontainers.image.revision=$Revision",
        "--label", "org.opencontainers.image.source=sourcecommit"
    )
}

Write-Host "Building $runtimeImage"
docker build @labelArguments --target runtime --tag $runtimeImage $resolvedContext
if ($LASTEXITCODE -ne 0) { throw "Runtime image build failed." }

Write-Host "Building $migrationImage"
docker build @labelArguments --target migration --tag $migrationImage $resolvedContext
if ($LASTEXITCODE -ne 0) { throw "Migration image build failed." }

docker push $runtimeImage
if ($LASTEXITCODE -ne 0) { throw "Runtime image push failed." }

docker push $migrationImage
if ($LASTEXITCODE -ne 0) { throw "Migration image push failed." }

Write-Host "Published both images with immutable tag $Tag."
