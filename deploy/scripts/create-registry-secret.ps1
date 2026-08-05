param(
    [string]$Namespace = "ncp-report",
    [string]$SecretName = "ncp-registry",
    [string]$Registry = "hhgee3ff.kr.private-ncr.ntruss.com"
)

$ErrorActionPreference = "Stop"

if ($Registry -notmatch '^[a-z0-9.-]+\.private-ncr\.ntruss\.com$') {
    throw "Registry must be an NCP Container Registry private endpoint."
}

$accessKey = (Read-Host "NCP registry Access Key ID").Trim()
if ([string]::IsNullOrWhiteSpace($accessKey)) {
    throw "Access Key ID is required."
}
$secureSecret = Read-Host "NCP registry Secret Key" -AsSecureString
$secretPointer = [IntPtr]::Zero
$secretKey = $null

try {
    $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $secureSecret
    )
    $secretKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        $secretPointer
    )
    if ([string]::IsNullOrWhiteSpace($secretKey)) {
        throw "Secret Key is required."
    }

    $existingNamespace = kubectl get namespace $Namespace `
        --ignore-not-found -o name
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to check namespace $Namespace."
    }
    if ([string]::IsNullOrWhiteSpace($existingNamespace)) {
        kubectl create namespace $Namespace | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create namespace $Namespace."
        }
    }

    $utf8 = [Text.Encoding]::UTF8
    $auth = [Convert]::ToBase64String(
        $utf8.GetBytes("${accessKey}:${secretKey}")
    )
    $dockerConfig = @{
        auths = @{
            $Registry = @{
                username = $accessKey
                password = $secretKey
                auth = $auth
            }
        }
    } | ConvertTo-Json -Compress -Depth 5
    $encodedConfig = [Convert]::ToBase64String(
        $utf8.GetBytes($dockerConfig)
    )
    $manifest = @{
        apiVersion = "v1"
        kind = "Secret"
        metadata = @{
            name = $SecretName
            namespace = $Namespace
        }
        type = "kubernetes.io/dockerconfigjson"
        data = @{
            ".dockerconfigjson" = $encodedConfig
        }
    } | ConvertTo-Json -Compress -Depth 5

    $manifest | kubectl apply -f - | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply registry pull Secret."
    }
    Write-Host "Registry pull Secret $Namespace/$SecretName is ready."
}
finally {
    $manifest = $null
    $existingNamespace = $null
    $encodedConfig = $null
    $dockerConfig = $null
    $auth = $null
    $secretKey = $null
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
}
