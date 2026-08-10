[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$ProjectId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]{1,80}$')]
    [string]$ExpectedProjectName,

    [ValidatePattern('^[A-Za-z0-9._-]{1,200}$')]
    [string]$ExpectedRepository = "architect_report",

    [ValidatePattern('^[A-Za-z0-9._/-]{1,200}$')]
    [string]$ExpectedBranch = "master",

    [ValidateRange(60, 7200)]
    [int]$TimeoutSeconds = 1800,

    [ValidateRange(2, 60)]
    [int]$PollSeconds = 10,

    [string]$CredentialFile = ".\deploy\private\.env.sourcebuild",

    [ValidatePattern('^[A-Z]{2}$')]
    [string]$RegionCode = "KR"
)

$ErrorActionPreference = "Stop"
$SourceBuildApiBase = "https://sourcebuild.apigw.ntruss.com"
$RequiredCredentialNames = @(
    "NCP_SOURCEBUILD_ACCESS_KEY",
    "NCP_SOURCEBUILD_SECRET_KEY"
)

function Read-SourceBuildCredentialFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "SourceBuild credential file was not found: $Path"
    }

    $credentials = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line -match '^\s*#') {
            continue
        }
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            throw "SourceBuild credential file contains an invalid line."
        }

        $name = $Matches[1]
        if ($RequiredCredentialNames -notcontains $name) {
            throw "Unsupported setting in SourceBuild credential file: $name"
        }
        if ($credentials.ContainsKey($name)) {
            throw "Duplicate setting in SourceBuild credential file: $name"
        }

        $value = $Matches[2]
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "SourceBuild credential setting is empty: $name"
        }
        $credentials[$name] = $value
    }

    foreach ($name in $RequiredCredentialNames) {
        if (-not $credentials.ContainsKey($name)) {
            throw "Required SourceBuild credential setting is missing: $name"
        }
    }
    return $credentials
}

function New-NcpSignature {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$RequestPath,
        [Parameter(Mandatory = $true)][string]$Timestamp,
        [Parameter(Mandatory = $true)][string]$AccessKey,
        [Parameter(Mandatory = $true)][string]$SecretKey
    )

    $message = "$Method $RequestPath`n$Timestamp`n$AccessKey"
    $secretBytes = [Text.Encoding]::UTF8.GetBytes($SecretKey)
    $messageBytes = [Text.Encoding]::UTF8.GetBytes($message)
    $hmac = New-Object Security.Cryptography.HMACSHA256 (,$secretBytes)
    try {
        return [Convert]::ToBase64String($hmac.ComputeHash($messageBytes))
    } finally {
        $hmac.Dispose()
        [Array]::Clear($secretBytes, 0, $secretBytes.Length)
        [Array]::Clear($messageBytes, 0, $messageBytes.Length)
    }
}

function Invoke-SourceBuildApi {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")]
        [string]$Method,
        [Parameter(Mandatory = $true)][string]$RequestPath,
        [Parameter(Mandatory = $true)][hashtable]$Credentials
    )

    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
    $accessKey = $Credentials["NCP_SOURCEBUILD_ACCESS_KEY"]
    $signature = New-NcpSignature `
        -Method $Method `
        -RequestPath $RequestPath `
        -Timestamp $timestamp `
        -AccessKey $accessKey `
        -SecretKey $Credentials["NCP_SOURCEBUILD_SECRET_KEY"]
    $headers = @{
        "x-ncp-apigw-timestamp" = $timestamp
        "x-ncp-iam-access-key" = $accessKey
        "x-ncp-apigw-signature-v2" = $signature
        "x-ncp-region_code" = $RegionCode
        "Content-Type" = "application/json"
    }

    try {
        return Invoke-RestMethod `
            -Method $Method `
            -Uri "$SourceBuildApiBase$RequestPath" `
            -Headers $headers `
            -TimeoutSec 30
    } catch {
        $statusCode = "unknown"
        if ($_.Exception.Response) {
            try {
                $statusCode = [int]$_.Exception.Response.StatusCode
            } catch {
                $statusCode = "unknown"
            }
        }
        throw "SourceBuild API request failed: method=$Method path=$RequestPath status=$statusCode"
    } finally {
        $headers.Clear()
        $signature = $null
        $accessKey = $null
    }
}

function Get-SourceBuildProject {
    param(
        [Parameter(Mandatory = $true)][int]$Id,
        [Parameter(Mandatory = $true)][hashtable]$Credentials
    )

    $response = Invoke-SourceBuildApi `
        -Method GET `
        -RequestPath "/api/v1/project/$Id" `
        -Credentials $Credentials
    if (-not $response.result) {
        throw "SourceBuild project response did not contain a result."
    }
    return $response.result
}

function Get-SourceBuildHistory {
    param(
        [Parameter(Mandatory = $true)][int]$Id,
        [Parameter(Mandatory = $true)][hashtable]$Credentials
    )

    $response = Invoke-SourceBuildApi `
        -Method GET `
        -RequestPath "/api/v1/project/$Id/history" `
        -Credentials $Credentials
    if (-not $response.result -or $null -eq $response.result.total) {
        throw "SourceBuild history response did not contain a result."
    }
    return $response.result
}

function Find-SourceBuildHistoryEntry {
    param(
        [Parameter(Mandatory = $true)]$History,
        [Parameter(Mandatory = $true)][string]$BuildId
    )

    foreach ($entry in @($History.history)) {
        if ([string]$entry.buildId -eq $BuildId) {
            return $entry
        }
    }
    return $null
}

function Resolve-SourceBuildTag {
    param(
        [Parameter(Mandatory = $true)]$History,
        [Parameter(Mandatory = $true)][string]$BuildId,
        [Parameter(Mandatory = $true)][string]$TagTemplate
    )

    if ($TagTemplate -notmatch '#') {
        throw "SourceBuild image tag template must contain '#': $TagTemplate"
    }

    # 실패·취소 이력은 레지스트리의 # 순번을 증가시키지 않는다. 따라서 전체
    # 이력 수가 아니라 성공한 빌드를 시간순으로 정렬해 실제 이미지 태그를 계산한다.
    $successfulEntries = @(
        @($History.history) |
            Where-Object { [string]$_.status -eq "success" } |
            Sort-Object -Property begin, buildId
    )
    for ($index = 0; $index -lt $successfulEntries.Count; $index++) {
        if ([string]$successfulEntries[$index].buildId -ne $BuildId) {
            continue
        }

        $buildNumber = $index + 1
        return [Text.RegularExpressions.Regex]::Replace(
            $TagTemplate,
            '#+',
            [string]$buildNumber
        )
    }
    throw "Completed build was not found in SourceBuild history: $BuildId"
}

function Format-SourceBuildTimestamp {
    param($Timestamp)

    if ($null -eq $Timestamp -or [string]::IsNullOrWhiteSpace([string]$Timestamp)) {
        return "unknown"
    }
    try {
        return [DateTimeOffset]::FromUnixTimeMilliseconds(
            [long]$Timestamp
        ).ToString("o")
    } catch {
        return "unknown"
    }
}

function Assert-ExpectedProject {
    param([Parameter(Mandatory = $true)]$Project)

    if ([int]$Project.id -ne $ProjectId) {
        throw "SourceBuild returned an unexpected project ID."
    }
    if ([string]$Project.name -ne $ExpectedProjectName) {
        throw "SourceBuild project name mismatch: expected=$ExpectedProjectName actual=$($Project.name)"
    }
    if ([string]$Project.source.type -ne "SourceCommit") {
        throw "SourceBuild project source must be SourceCommit."
    }
    if ([string]$Project.source.config.repository -ne $ExpectedRepository) {
        throw "SourceBuild repository mismatch."
    }
    if ([string]$Project.source.config.branch -ne $ExpectedBranch) {
        throw "SourceBuild branch mismatch."
    }
    if (-not [bool]$Project.cmd.dockerbuild.use) {
        throw "SourceBuild Docker image build is disabled."
    }
    if ([string]$Project.cmd.dockerbuild.tag -notmatch '#') {
        throw "SourceBuild Docker image tag is not build-numbered."
    }
}

$credentials = Read-SourceBuildCredentialFile -Path $CredentialFile
try {
    $project = Get-SourceBuildProject `
        -Id $ProjectId `
        -Credentials $credentials
    Assert-ExpectedProject -Project $project

    $target = "$($project.name) ($ProjectId)"
    if (-not $PSCmdlet.ShouldProcess($target, "Start NCP SourceBuild")) {
        Write-Host (
            "Validated SourceBuild project without starting a build: " +
            "id=$ProjectId name=$($project.name) " +
            "repository=$ExpectedRepository branch=$ExpectedBranch " +
            "tagTemplate=$($project.cmd.dockerbuild.tag)"
        )
        return
    }

    $buildResponse = Invoke-SourceBuildApi `
        -Method POST `
        -RequestPath "/api/v1/project/$ProjectId/build" `
        -Credentials $credentials
    $buildId = [string]$buildResponse.result.buildId
    if ([string]::IsNullOrWhiteSpace($buildId)) {
        throw "SourceBuild start response did not contain a build ID."
    }
    if ([int]$buildResponse.result.projectId -ne $ProjectId) {
        throw "SourceBuild start response returned an unexpected project ID."
    }

    Write-Host "Started SourceBuild: project=$($project.name) buildId=$buildId"
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $lastStatus = "not-listed"
    $historyEntry = $null
    $history = $null
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $history = Get-SourceBuildHistory `
            -Id $ProjectId `
            -Credentials $credentials
        $historyEntry = Find-SourceBuildHistoryEntry `
            -History $history `
            -BuildId $buildId
        if ($historyEntry) {
            $status = [string]$historyEntry.status
            if ($status -ne $lastStatus) {
                Write-Host (
                    "SourceBuild status: project=$($project.name) " +
                    "buildId=$buildId status=$status"
                )
                $lastStatus = $status
            }
            if ($status -eq "success") {
                break
            }
            if ($status -in @("fail", "canceled")) {
                $failedPhase = [string]$historyEntry.failedPhase
                if ([string]::IsNullOrWhiteSpace($failedPhase)) {
                    $failedPhase = "unknown"
                }
                throw (
                    "SourceBuild did not succeed: project=$($project.name) " +
                    "buildId=$buildId status=$status failedPhase=$failedPhase " +
                    "begin=$(Format-SourceBuildTimestamp $historyEntry.begin) " +
                    "end=$(Format-SourceBuildTimestamp $historyEntry.end)"
                )
            }
        }
        Start-Sleep -Seconds $PollSeconds
    }
    $stopwatch.Stop()

    if (-not $historyEntry -or [string]$historyEntry.status -ne "success") {
        throw (
            "SourceBuild timed out: project=$($project.name) buildId=$buildId " +
            "lastStatus=$lastStatus timeoutSeconds=$TimeoutSeconds"
        )
    }

    # 성공 응답 직후 이력을 다시 읽어 확정된 성공 빌드 순번으로 build-N을 계산한다.
    $history = Get-SourceBuildHistory `
        -Id $ProjectId `
        -Credentials $credentials
    $tag = Resolve-SourceBuildTag `
        -History $history `
        -BuildId $buildId `
        -TagTemplate ([string]$project.cmd.dockerbuild.tag)

    [pscustomobject]@{
        ProjectId = $ProjectId
        ProjectName = [string]$project.name
        BuildId = $buildId
        Status = "success"
        Image = [string]$project.cmd.dockerbuild.image
        Tag = $tag
        Begin = Format-SourceBuildTimestamp $historyEntry.begin
        End = Format-SourceBuildTimestamp $historyEntry.end
        ElapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
    }
} finally {
    if ($credentials) {
        foreach ($name in @($credentials.Keys)) {
            $credentials[$name] = $null
        }
        $credentials.Clear()
    }
}
