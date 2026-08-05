#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [Parameter(Mandatory = $true)][string]$DisplayName,
    [Parameter(Mandatory = $true)][string]$TenantCode,
    [ValidateSet("CUSTOMER_VIEWER", "CUSTOMER_ADMIN")]
    [string]$Role = "CUSTOMER_VIEWER"
)

$ProjectDir = $PSScriptRoot
$composeArguments = @(
    "compose", "-p", "ncp-report",
    "--env-file", (Join-Path $ProjectDir ".env.db"),
    "--env-file", (Join-Path $ProjectDir ".env.service"),
    "-f", (Join-Path $ProjectDir "compose.yaml"),
    "--profile", "tools", "run", "--rm", "report-runner",
    "python", "-m", "webapp.cli", "create-customer-user",
    "--email", $Email,
    "--display-name", $DisplayName,
    "--tenant-code", $TenantCode,
    "--role", $Role
)
& docker @composeArguments
if ($LASTEXITCODE -ne 0) { throw "Customer user setup failed." }
