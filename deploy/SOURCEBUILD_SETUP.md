# NCP cloud build setup

Local Docker builds are disabled for normal releases. NCP SourceBuild builds
the runtime image from the `architect_report` SourceCommit `master` branch.
A separate least-privilege migration image is built only for database schema
releases. SourceBuild uploads images to the `architect-report-build` Container
Registry; the deployment script only updates NKS to the resulting tags. The
expected authenticated endpoint is
`architect-report-build.kr.ncr.ntruss.com`. Enabling this endpoint does not make
the registry publicly readable; keep the separate Public Registry option
disabled.

## Project 1: application runtime

Create a SourceBuild project with these basic and environment settings:

| Field | Value |
| --- | --- |
| Project name | `architect-report-runtime` |
| Build target | SourceCommit |
| Repository | `architect_report` |
| Branch | `master` |
| Build environment source | SourceBuild-managed image |
| OS | Ubuntu 20.04 |
| Runtime | Python 3.13 |
| Docker image build | Enabled |
| Docker engine | 20.10.18 |
| Compute | Smallest type sufficient for the pilot |
| Timeout | 20 minutes |
| Environment variables | None |

Command before build:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Command during build:

```sh
python -m pytest -q
```

Command after build:

```sh
python -m compileall -q app collectors database normalizers utils webapp
```

Docker image build settings:

| Field | Value |
| --- | --- |
| Use Docker image build | Enabled |
| Dockerfile path | `Dockerfile.runtime` |
| Container Registry | `architect-report-build` |
| Image name | `ncp-report` |
| Image tag | `build-#` |
| Set latest tag | Enabled |

Upload settings:

| Field | Value |
| --- | --- |
| Save build artifact | Disabled |
| Artifact path | Empty |
| Object Storage bucket/folder/file name | Empty |
| Upload completed build environment image | Disabled |

The image configured under **Docker image build settings** is already built
from `Dockerfile.runtime` and uploaded to Container Registry. "Upload completed
build environment image" saves the SourceBuild worker environment itself and
is not the application image, so leave it disabled.

Additional service integrations for the pilot:

| Field | Value |
| --- | --- |
| Cloud Log Analytics | Disabled initially |
| File Safer | Disabled initially |
| Build start/end notifications | Optional |

Console logs are sufficient for the first build. Enable Cloud Log Analytics
later only when longer build-log retention is required.

## Project 2: database migration

Create a second SourceBuild project:

| Field | Value |
| --- | --- |
| Project name | `architect-report-migration` |
| Build target | SourceCommit |
| Repository / branch | `architect_report` / `master` |
| Build environment source | SourceBuild-managed image |
| OS / runtime | Ubuntu 20.04 / base |
| Docker image build | Enabled, Docker engine 20.10.18 |
| Compute | Smallest type |
| Timeout | 10 minutes |
| Environment variables | None |

Migration build commands:

| Phase | Command |
| --- | --- |
| Before build | `test -f Dockerfile.migration` |
| During build | `test -d database/schema` |
| After build | `echo "Migration image source validation complete."` |

Migration Docker image settings:

| Field | Value |
| --- | --- |
| Dockerfile path | `Dockerfile.migration` |
| Container Registry | `architect-report-build` |
| Image name | `ncp-report-migrate` |
| Image tag | `build-#` |
| Set latest tag | Enabled |

Migration upload and integrations:

| Field | Value |
| --- | --- |
| Save build artifact | Disabled |
| Upload completed build environment image | Disabled |
| Cloud Log Analytics | Disabled initially |
| File Safer | Disabled initially |

The runtime project owns the full tests. Do not put the migration project in
the routine runtime pipeline. Run it deliberately only when `database/schema`
or the migration runner changes.

## Start cloud builds from PowerShell

The build API credential is separate from the report API credential and the
NKS Container Registry pull credential. Store only these two entries in the
ignored `deploy/private/.env.sourcebuild` file:

```text
NCP_SOURCEBUILD_ACCESS_KEY=...
NCP_SOURCEBUILD_SECRET_KEY=...
```

Validate the saved credential and both project configurations without starting
a build:

```powershell
.\deploy\scripts\run-sourcebuild.ps1 `
  -ProjectId 53175 `
  -ExpectedProjectName architect-report-runtime `
  -WhatIf

.\deploy\scripts\run-sourcebuild.ps1 `
  -ProjectId 53205 `
  -ExpectedProjectName architect-report-migration `
  -WhatIf
```

After the reviewed commit is present on SourceCommit `master`, start the
required projects. The script signs the official SourceBuild API request,
tracks the exact returned build ID, stops on failure or timeout, and returns
the final `build-N` tag without printing either credential.

```powershell
$runtimeBuild = .\deploy\scripts\run-sourcebuild.ps1 `
  -ProjectId 53175 `
  -ExpectedProjectName architect-report-runtime

# Run this only for a schema release.
$migrationBuild = .\deploy\scripts\run-sourcebuild.ps1 `
  -ProjectId 53205 `
  -ExpectedProjectName architect-report-migration
```

Do not substitute values from `~/.ncloud/configure`; that credential is used
for the NKS/registry path and is not the SourceBuild API identity.

## Deploy cloud-built tags

After the runtime SourceBuild project succeeds, copy its immutable `build-N`
tag and the full SourceCommit SHA. This command performs no Docker build:

```powershell
$env:Path = "C:\Tools\ncp;C:\Tools\helm;$env:Path"
$sourceRevision = (git rev-parse HEAD).Trim().ToLowerInvariant()
.\deploy\scripts\deploy-sourcebuild-images.ps1 `
  -RuntimeTag $runtimeBuild.Tag `
  -SourceRevision $sourceRevision `
  -Helm "C:\Tools\helm\helm.exe"
```

For a schema release, build the migration image from the same commit and add:

```powershell
  -EnableMigration -MigrationTag $migrationBuild.Tag
```

The script rejects a revision that does not equal SourceCommit `master`, then
performs an atomic Helm rollout. Kubernetes pulls through the authenticated
registry private endpoint. Local Docker is not used.

## Pipeline stage after the first cloud build

Once the runtime project is proven independently, create a SourcePipeline triggered
by SourceCommit `master`:

1. SourceCommit trigger (`architect_report/master`).
2. Runtime SourceBuild project; tests and runtime image.
3. Controlled SourceDeploy stage for the NKS runtime objects.

SourceDeploy uses the committed `deploy/sourcedeploy/runtime.yaml` manifest for
routine application rollouts. Database migration remains a separate,
deliberate Helm operation and is not part of the automatic runtime pipeline.
The runtime Deployments retain their schema-wait init containers even when the
migration Job is omitted, so schema releases must apply the reviewed migration
before the new rollout can become ready.
See `deploy/SOURCEPIPELINE_SETUP.md` for the console configuration.
