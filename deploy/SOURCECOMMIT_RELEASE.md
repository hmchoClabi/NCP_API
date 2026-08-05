# SourceCommit-based release

> Normal local image builds are disabled. Configure NCP SourceBuild with
> `deploy/SOURCEBUILD_SETUP.md`. The legacy local builder now requires the
> explicit emergency-only `-AllowLocalBuild` switch.

The release source of truth is the commit pushed to NCP SourceCommit. The
release script refuses dirty working trees, runs tests, pushes `HEAD`, verifies
the remote branch SHA, labels both images with that full SHA, and only then
builds and deploys them.

## One-time setup

Copy the HTTPS clone URL from the SourceCommit repository page. Do not put a
Git password or NCP API key in the URL or any project file.

```powershell
.\deploy\scripts\configure-sourcecommit.ps1 `
  -RepositoryUrl "https://devtools.ncloud.com/REPLACE_WITH_CLONE_URL"
```

Authenticate interactively when Git requests the SourceCommit username and Git
password. Confirm both remotes afterward:

```powershell
git remote -v
```

`origin` may continue to point to GitHub; `sourcecommit` is the release remote.

## Release procedure

Review and commit changes on `master` before release:

```powershell
git status
git add --all
git diff --cached --check
git commit -m "Describe the release"
```

Emergency-only local release:

```powershell
$env:Path = "C:\Tools\ncp;C:\Tools\helm;$env:Path"
.\deploy\scripts\release-from-sourcecommit.ps1 `
  -Helm "C:\Tools\helm\helm.exe" `
  -AllowLocalBuild
```

The image tag is derived from the commit, for example `git-a1b2c3d4e5f6`.
Rerunning the same commit creates the same release identity. Kubernetes pulls
over the registry private endpoint configured in `values-pilot.yaml`.

Use `-SkipDeploy` only when publishing images for a later controlled rollout.
`-SkipTests` exists for emergency diagnosis and must not be used for a normal
release.

## Secrets

The following stay outside SourceCommit:

- `.env`, `.env.db`, `.env.service`;
- `deploy/private/` generated Kubernetes secret material;
- `secrets/`, reports, logs and local database files;
- legacy per-customer PowerShell launchers that contain injected credentials.

NKS continues to receive runtime secrets through the existing Kubernetes
Secret. SourceCommit stores application and deployment source only.
