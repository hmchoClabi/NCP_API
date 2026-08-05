#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [string]$DisplayName = "MSP Administrator"
)

$ProjectDir = $PSScriptRoot
$composeArguments = @(
    "compose", "-p", "ncp-report",
    "--env-file", (Join-Path $ProjectDir ".env.db"),
    "--env-file", (Join-Path $ProjectDir ".env.service"),
    "-f", (Join-Path $ProjectDir "compose.yaml"),
    "--profile", "tools", "run", "--rm", "report-runner",
    "python", "-m", "webapp.cli", "bootstrap-admin",
    "--email", $Email, "--display-name", $DisplayName
)
& docker @composeArguments
if ($LASTEXITCODE -ne 0) { throw "MSP administrator setup failed." }
