param(
    [string]$Namespace = "ncp-report",
    [string]$SecretName = "ncp-report-secrets",
    [string]$EnvFile = "deploy/private/.env.k8s",
    [string]$MasterKeyFile = "deploy/private/credential-master-key"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Secret environment file not found: $EnvFile"
}
if (-not (Test-Path -LiteralPath $MasterKeyFile -PathType Leaf)) {
    throw "Credential master key not found: $MasterKeyFile"
}

$existingNamespace = kubectl get namespace $Namespace `
    --ignore-not-found -o name
if ($LASTEXITCODE -ne 0) {
    throw "Failed to check namespace $Namespace."
}
if ([string]::IsNullOrWhiteSpace($existingNamespace)) {
    kubectl create namespace $Namespace | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create namespace $Namespace." }
}

$temporaryDirectory = Join-Path (
    [IO.Path]::GetTempPath()
) "ncp-report-secret-$([guid]::NewGuid().ToString('N'))"
$resolvedTemporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$resolvedTemporaryDirectory = [IO.Path]::GetFullPath($temporaryDirectory)
if (-not $resolvedTemporaryDirectory.StartsWith(
    $resolvedTemporaryRoot, [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to create a temporary secret directory outside the OS temp path."
}

try {
    New-Item -ItemType Directory -Path $resolvedTemporaryDirectory | Out-Null
    if ($env:OS -eq "Windows_NT") {
        icacls $resolvedTemporaryDirectory /inheritance:r | Out-Null
        icacls $resolvedTemporaryDirectory /grant:r `
            "$($env:USERNAME):(OI)(CI)(F)" | Out-Null
    }

    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    foreach ($line in Get-Content -LiteralPath $EnvFile) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_.-]*)=(.*)$') { continue }
        $keyPath = Join-Path $resolvedTemporaryDirectory $matches[1]
        [IO.File]::WriteAllText($keyPath, $matches[2], $utf8NoBom)
    }
    Copy-Item -LiteralPath $MasterKeyFile `
        -Destination (Join-Path $resolvedTemporaryDirectory "credential-master-key")

    $manifest = kubectl -n $Namespace create secret generic $SecretName `
        "--from-file=$resolvedTemporaryDirectory" `
        --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to render Kubernetes Secret." }
    $manifest | kubectl apply -f - | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to apply Kubernetes Secret." }
}
finally {
    $manifest = $null
    if (Test-Path -LiteralPath $resolvedTemporaryDirectory) {
        Remove-Item -LiteralPath $resolvedTemporaryDirectory -Recurse -Force
    }
}

Write-Host "Secret $Namespace/$SecretName is ready. Secret values were not printed."
