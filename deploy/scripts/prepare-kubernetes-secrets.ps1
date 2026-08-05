param(
    [string]$DatabaseEnvFile = ".env.db",
    [string]$ServiceEnvFile = ".env.service",
    [string]$MailEnvFile = ".env",
    [string]$MasterKeyFile = "secrets/credential-master-key",
    [string]$OutputDirectory = "deploy/private"
)

$ErrorActionPreference = "Stop"

function Read-EnvironmentFile([string]$Path, [bool]$Required) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        if ($Required) { throw "Required environment file not found: $Path" }
        return @{}
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $values[$matches[1]] = $matches[2]
    }
    return $values
}

$databaseValues = Read-EnvironmentFile $DatabaseEnvFile $true
$serviceValues = Read-EnvironmentFile $ServiceEnvFile $true
$mailValues = Read-EnvironmentFile $MailEnvFile $false

$requiredKeys = @(
    "DB_ADMIN_USER",
    "DB_ADMIN_PASSWORD",
    "DB_CONTROL_APP_PASSWORD",
    "DB_PUBLIC_WORKER_PASSWORD",
    "DB_GOV_WORKER_PASSWORD",
    "DB_MSP_APP_PASSWORD"
)
foreach ($name in $requiredKeys) {
    if ([string]::IsNullOrWhiteSpace($databaseValues[$name])) {
        throw "Required database setting is missing: $name"
    }
}
if ([string]::IsNullOrWhiteSpace($serviceValues["WEB_SECRET_KEY"])) {
    throw "Required service setting is missing: WEB_SECRET_KEY"
}
if (-not (Test-Path -LiteralPath $MasterKeyFile -PathType Leaf)) {
    throw "Credential master key not found: $MasterKeyFile"
}

$selected = [ordered]@{}
foreach ($name in $requiredKeys) { $selected[$name] = $databaseValues[$name] }
$selected["WEB_SECRET_KEY"] = $serviceValues["WEB_SECRET_KEY"]

$mailKeys = @(
    "SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "SMTP_USERNAME",
    "SMTP_PASSWORD", "SMTP_USE_TLS", "SMTP_USE_SSL", "SMTP_TIMEOUT"
)
foreach ($name in $mailKeys) {
    if ($mailValues.ContainsKey($name)) { $selected[$name] = $mailValues[$name] }
}

New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$outputEnv = Join-Path $OutputDirectory ".env.k8s"
$outputMasterKey = Join-Path $OutputDirectory "credential-master-key"
$lines = foreach ($entry in $selected.GetEnumerator()) {
    if ($entry.Value -match "[`r`n]") {
        throw "Multiline values are not supported: $($entry.Key)"
    }
    "$($entry.Key)=$($entry.Value)"
}
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllLines((Join-Path (Get-Location) $outputEnv), $lines, $utf8NoBom)
Copy-Item -LiteralPath $MasterKeyFile -Destination $outputMasterKey -Force

if ($IsWindows -or $env:OS -eq "Windows_NT") {
    icacls $outputEnv /inheritance:r | Out-Null
    icacls $outputEnv /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    icacls $outputMasterKey /inheritance:r | Out-Null
    icacls $outputMasterKey /grant:r "$($env:USERNAME):(R,W)" | Out-Null
}

Write-Host "Prepared Kubernetes secret inputs without printing their values:"
Write-Host "- $outputEnv"
Write-Host "- $outputMasterKey"
Write-Host "The global NCP_ACCESS_KEY/NCP_SECRET_KEY values were intentionally excluded."
