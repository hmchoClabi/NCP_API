param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[^\s]+$')]
    [string]$RepositoryUrl,
    [string]$Remote = "sourcecommit"
)

$ErrorActionPreference = "Stop"

if ($Remote -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Remote name contains unsupported characters."
}
if ($RepositoryUrl -notmatch '^https://devtools\.ncloud\.com/') {
    throw "RepositoryUrl must be an NCP SourceCommit HTTPS clone URL."
}

git rev-parse --is-inside-work-tree | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Run this script inside the Git repository." }

$existing = git remote
if ($existing -contains $Remote) {
    git remote set-url $Remote $RepositoryUrl
} else {
    git remote add $Remote $RepositoryUrl
}
if ($LASTEXITCODE -ne 0) { throw "Unable to configure the SourceCommit remote." }

Write-Host "Configured Git remote '$Remote'. Credentials were not stored in the repository."
git remote get-url $Remote
