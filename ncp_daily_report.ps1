#requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ===========================================================================
# NCP 고객별 보고서 PowerShell 일괄 실행
# ===========================================================================

# run_ncp_daily_report.ps1이 위치한 프로젝트 루트 폴더
$ProjectDir = $PSScriptRoot

# 하위 스크립트를 별도 프로세스로 실행할 Windows PowerShell
$PowerShellExe = Join-Path `
    $env:SystemRoot `
    "System32\WindowsPowerShell\v1.0\powershell.exe"

# 로그 설정
$LogDir = Join-Path $ProjectDir "logs\scheduler"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path `
    $LogDir `
    "ncp_daily_report_$Timestamp.log"

# 한글 출력 설정
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# ===========================================================================
# 실행할 고객별 PS1 파일
#
# 아래 배열에 작성된 순서대로 실행됩니다.
# 새로운 고객 스크립트를 추가하면 이 배열에 파일명을 추가하세요.
# ===========================================================================

$TargetScripts = @(
    "cne2.ps1"
    "dongaaadmin.ps1"
    "gbe2.ps1"
    "gbsa.ps1"
    "kea.ps1"
    "konfort.ps1"
    "kosis2.ps1"
    "nfram.ps1"
    "sbiz.ps1"
)

# ===========================================================================
# 실행 전 검증
# ===========================================================================

if (-not (Test-Path -LiteralPath $ProjectDir)) {
    throw "프로젝트 경로를 찾을 수 없습니다: $ProjectDir"
}

if (-not (Test-Path -LiteralPath $PowerShellExe)) {
    throw "Windows PowerShell을 찾을 수 없습니다: $PowerShellExe"
}

New-Item `
    -ItemType Directory `
    -Path $LogDir `
    -Force | Out-Null

# 실행 결과 저장
$Results = @()

# ===========================================================================
# 로그 시작
# ===========================================================================

@(
    "======================================================================"
    "NCP 고객별 일간 보고서 일괄 작업 시작"
    "실행 시각 : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "프로젝트  : $ProjectDir"
    "실행 파일 : $($TargetScripts.Count)개"
    "로그 파일 : $LogFile"
    "======================================================================"
) | Tee-Object `
    -FilePath $LogFile

# ===========================================================================
# 고객별 PS1 순차 실행
# ===========================================================================

Push-Location $ProjectDir

try {
    foreach ($ScriptName in $TargetScripts) {
        $ScriptPath = Join-Path $ProjectDir $ScriptName
        $StartedAt = Get-Date
        $ScriptExitCode = 1
        $Status = "FAILED"
        $ErrorMessage = ""

        @(
            ""
            "----------------------------------------------------------------------"
            "작업 시작 : $ScriptName"
            "시작 시각 : $($StartedAt.ToString('yyyy-MM-dd HH:mm:ss'))"
            "파일 경로 : $ScriptPath"
            "----------------------------------------------------------------------"
        ) | Tee-Object `
            -FilePath $LogFile `
            -Append

        if (-not (Test-Path -LiteralPath $ScriptPath)) {
            $ErrorMessage = "스크립트 파일을 찾을 수 없습니다."

            "오류: $ErrorMessage $ScriptPath" |
                Tee-Object `
                    -FilePath $LogFile `
                    -Append

            $Results += [PSCustomObject]@{
                ScriptName  = $ScriptName
                Status      = $Status
                ExitCode    = $ScriptExitCode
                StartedAt   = $StartedAt
                FinishedAt  = Get-Date
                Error       = $ErrorMessage
            }

            # 다음 고객 스크립트는 계속 실행
            continue
        }

        try {
            # 각 PS1을 별도의 PowerShell 프로세스로 실행합니다.
            #
            # 하위 PS1에서 exit를 사용하더라도
            # run_ncp_daily_report.ps1 자체가 종료되지 않습니다.
            & $PowerShellExe `
                -NoProfile `
                -NonInteractive `
                -ExecutionPolicy Bypass `
                -File $ScriptPath 2>&1 |
                Tee-Object `
                    -FilePath $LogFile `
                    -Append

            $ScriptExitCode = $LASTEXITCODE

            if ($ScriptExitCode -eq 0) {
                $Status = "SUCCESS"
            }
            else {
                $ErrorMessage = (
                    "PowerShell 종료 코드가 0이 아닙니다: {0}" -f
                    $ScriptExitCode
                )
            }
        }
        catch {
            $ScriptExitCode = 1
            $ErrorMessage = $_.Exception.Message

            "실행 예외: $ErrorMessage" |
                Tee-Object `
                    -FilePath $LogFile `
                    -Append
        }

        $FinishedAt = Get-Date
        $ElapsedSeconds = (
            $FinishedAt - $StartedAt
        ).TotalSeconds

        $Results += [PSCustomObject]@{
            ScriptName  = $ScriptName
            Status      = $Status
            ExitCode    = $ScriptExitCode
            StartedAt   = $StartedAt
            FinishedAt  = $FinishedAt
            Error       = $ErrorMessage
        }

        @(
            "----------------------------------------------------------------------"
            "작업 완료 : $ScriptName"
            "상태      : $Status"
            "종료 코드 : $ScriptExitCode"
            "소요 시간 : $([math]::Round($ElapsedSeconds, 1))초"
            "완료 시각 : $($FinishedAt.ToString('yyyy-MM-dd HH:mm:ss'))"
            "----------------------------------------------------------------------"
        ) | Tee-Object `
            -FilePath $LogFile `
            -Append
    }
}
finally {
    Pop-Location
}

# ===========================================================================
# 전체 실행 결과
# ===========================================================================

$SuccessResults = @(
    $Results | Where-Object {
        $_.Status -eq "SUCCESS"
    }
)

$FailedResults = @(
    $Results | Where-Object {
        $_.Status -ne "SUCCESS"
    }
)

@(
    ""
    "======================================================================"
    "NCP 고객별 일간 보고서 실행 결과"
    "======================================================================"
) | Tee-Object `
    -FilePath $LogFile `
    -Append

foreach ($Result in $Results) {
    $ResultLine = (
        "{0,-22} 상태={1,-7} 종료코드={2}" -f
        $Result.ScriptName,
        $Result.Status,
        $Result.ExitCode
    )

    $ResultLine |
        Tee-Object `
            -FilePath $LogFile `
            -Append

    if ($Result.Error) {
        "  오류: $($Result.Error)" |
            Tee-Object `
                -FilePath $LogFile `
                -Append
    }
}

@(
    ""
    "전체 작업 수 : $($Results.Count)"
    "성공 작업 수 : $($SuccessResults.Count)"
    "실패 작업 수 : $($FailedResults.Count)"
    "종료 시각    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "로그 파일    : $LogFile"
    "======================================================================"
) | Tee-Object `
    -FilePath $LogFile `
    -Append

# 하나라도 실패한 경우 작업 스케줄러에 실패로 표시
if ($FailedResults.Count -gt 0) {
    exit 1
}

exit 0