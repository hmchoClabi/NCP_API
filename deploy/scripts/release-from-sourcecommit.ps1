param(
    [string]$Remote = "sourcecommit",
    [string]$Branch = "main",
    [string]$Registry = "architect-ncp-report.kr.ncr.ntruss.com",
    [string]$Namespace = "ncp-report",
    [string]$Release = "ncp-report",
    [string]$ValuesFile = ".\deploy\helm\ncp-report\values-pilot.yaml",
    [string]$Helm = "helm",
    [switch]$SkipTests,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"

if ($Remote -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid remote name." }
if ($Branch -notmatch '^[A-Za-z0-9._/-]+$') { throw "Invalid branch name." }
if (-not (Test-Path -LiteralPath $ValuesFile)) { throw "Values file not found." }

git rev-parse --is-inside-work-tree | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Run this script inside the Git repository." }
if (-not ((git remote) -contains $Remote)) {
    throw "Git remote '$Remote' is not configured. Run configure-sourcecommit.ps1 first."
}

$changes = git status --porcelain=v1 --untracked-files=all
if ($changes) {
    throw "The working tree is not clean. Commit reviewed changes before releasing."
}

$revision = (git rev-parse HEAD).Trim().ToLowerInvariant()
if ($revision -notmatch '^[0-9a-f]{40}$') { throw "Unable to resolve Git HEAD." }
$shortRevision = $revision.Substring(0, 12)
$tag = "git-$shortRevision"

if (-not $SkipTests) {
    & .\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; source was not pushed." }
}

git push $Remote "HEAD:refs/heads/$Branch"
if ($LASTEXITCODE -ne 0) { throw "SourceCommit push failed." }

$remoteLine = git ls-remote $Remote "refs/heads/$Branch"
if ($LASTEXITCODE -ne 0 -or -not $remoteLine) {
    throw "Unable to verify the SourceCommit branch."
}
$remoteRevision = ($remoteLine -split '\s+')[0].ToLowerInvariant()
if ($remoteRevision -ne $revision) {
    throw "SourceCommit branch does not match local HEAD; build aborted."
}
$postPushChanges = git status --porcelain=v1 --untracked-files=all
if ($postPushChanges) {
    throw "The working tree changed after SourceCommit verification; build aborted."
}

& .\deploy\scripts\build-and-push.ps1 `
    -Registry $Registry -Tag $tag -Context "." -Revision $revision
if ($LASTEXITCODE -ne 0) { throw "Image publication failed." }

if (-not $SkipDeploy) {
    & $Helm upgrade --install $Release .\deploy\helm\ncp-report `
        --namespace $Namespace --create-namespace `
        -f $ValuesFile `
        --set-string "image.tag=$tag" `
        --set-string "migration.image.tag=$tag" `
        --atomic --wait --timeout 10m
    if ($LASTEXITCODE -ne 0) { throw "Helm deployment failed." }
}

Write-Host "Released verified SourceCommit revision $revision as $tag."
