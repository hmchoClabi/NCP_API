param(
    [string]$Namespace = "ncp-report",
    [string]$Helm = "helm",
    [string]$ValuesFile = ".\deploy\helm\ncp-report\values-pilot.yaml",
    [string]$OutputFile = ".\deploy\sourcedeploy\runtime.yaml"
)

$ErrorActionPreference = "Stop"
$chart = ".\deploy\helm\ncp-report"

if (-not (Test-Path -LiteralPath $ValuesFile)) {
    throw "Values file not found."
}
$outputDirectory = Split-Path -Parent $OutputFile
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$manifest = & $Helm template ncp-report $chart `
    --namespace $Namespace `
    -f $ValuesFile `
    --set-string 'image.repository=${registry_endpoint}/ncp-report' `
    --set-string 'image.tag=latest' `
    --set-string 'sourceRevision=sourcepipeline' `
    --set migration.enabled=false `
    --show-only templates/deployments.yaml `
    --show-only templates/hpa.yaml
if ($LASTEXITCODE -ne 0) { throw "Helm template failed." }

$content = ($manifest -join "`n") + "`n"
$content = $content.Replace(
    "app.kubernetes.io/managed-by: Helm",
    "app.kubernetes.io/managed-by: SourceDeploy"
)
if ($content -notmatch '\$\{registry_endpoint\}/ncp-report:latest') {
    throw "SourceDeploy registry placeholder was not rendered."
}
if ($content -match 'kind: Job') {
    throw "Runtime manifest must not contain a migration Job."
}
if ($content -notmatch 'kind: HorizontalPodAutoscaler') {
    throw "Runtime manifest must contain the enabled HPA resources."
}

$utf8WithoutBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText(
    (Join-Path (Get-Location) $OutputFile),
    $content,
    $utf8WithoutBom
)
Write-Host "Generated SourceDeploy manifest: $OutputFile"
