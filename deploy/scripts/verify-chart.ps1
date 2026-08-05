$ErrorActionPreference = "Stop"
$chart = "deploy/helm/ncp-report"
$values = "$chart/values-pilot.yaml"
$output = Join-Path ([System.IO.Path]::GetTempPath()) "ncp-report-rendered.yaml"

if (-not (Get-Command helm -ErrorAction SilentlyContinue)) {
    throw "helm is required to validate the deployment package."
}

helm lint $chart --values $values `
    --set image.repository=registry.example/ncp-report `
    --set image.tag=test `
    --set migration.image.repository=registry.example/ncp-report-migrate `
    --set migration.image.tag=test
if ($LASTEXITCODE -ne 0) { throw "helm lint failed." }

helm template ncp-report $chart --namespace ncp-report --values $values `
    --set image.repository=registry.example/ncp-report `
    --set image.tag=test `
    --set migration.image.repository=registry.example/ncp-report-migrate `
    --set migration.image.tag=test | Set-Content -LiteralPath $output -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "helm template failed." }

Write-Host "Rendered manifest: $output"
