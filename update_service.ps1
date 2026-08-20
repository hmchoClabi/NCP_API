#requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$ServiceEnvFile = Join-Path $ProjectDir ".env.service"
if (-not (Test-Path -LiteralPath $ServiceEnvFile)) {
    throw "Run setup_service.ps1 first."
}

$tag = "local-$(Get-Date -Format 'yyyyMMddHHmmss')"
$lines = [System.IO.File]::ReadAllLines($ServiceEnvFile)
$found = $false
for ($index = 0; $index -lt $lines.Length; $index++) {
    if ($lines[$index].StartsWith("IMAGE_TAG=")) {
        $lines[$index] = "IMAGE_TAG=$tag"
        $found = $true
    }
}
if (-not $found) { $lines += "IMAGE_TAG=$tag" }
[System.IO.File]::WriteAllLines(
    $ServiceEnvFile, $lines,
    [System.Text.UTF8Encoding]::new($false)
)

$composeArguments = @(
    "compose", "-p", "ncp-report",
    "--env-file", (Join-Path $ProjectDir ".env.db"),
    "--env-file", $ServiceEnvFile,
    "-f", (Join-Path $ProjectDir "compose.yaml")
)
& docker @composeArguments build web
if ($LASTEXITCODE -ne 0) { throw "Docker image build failed." }
& docker @composeArguments up -d postgres migrate web scheduler artifact-cleanup worker-public worker-gov
if ($LASTEXITCODE -ne 0) { throw "Service update failed." }

$deadline = (Get-Date).AddSeconds(180)
do {
    $health = (& docker inspect --format "{{.State.Health.Status}}" ncp-report-web 2>$null).Trim()
    if ($health -eq "healthy") { break }
    if ($health -eq "unhealthy") {
        & docker @composeArguments logs --tail 80 web
        throw "Updated web service health check failed."
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if ($health -ne "healthy") { throw "Updated web service did not become healthy in time." }

& docker @composeArguments ps
