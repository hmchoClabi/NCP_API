# NCP cloud build setup

Local Docker builds are disabled for normal releases. NCP SourceBuild builds
two least-privilege images from the `architect_report` SourceCommit `master`
branch. SourceBuild uploads both images to `architect-ncp-report` Container
Registry; the deployment script only updates NKS to the resulting tags. The
expected authenticated endpoint is
`architect-ncp-report.kr.ncr.ntruss.com`. Enabling this endpoint does not make
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
| Container Registry | `architect-ncp-report` |
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
| Container Registry | `architect-ncp-report` |
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

The runtime project owns the full tests. Configure the pipeline so the
migration build starts only after the runtime build succeeds.

## Deploy cloud-built tags

After both SourceBuild projects succeed, copy their immutable `build-N` tags
and the full SourceCommit SHA. This command performs no Docker build:

```powershell
$env:Path = "C:\Tools\ncp;C:\Tools\helm;$env:Path"
.\deploy\scripts\deploy-sourcebuild-images.ps1 `
  -RuntimeTag "build-1" `
  -MigrationTag "build-1" `
  -SourceRevision "FULL_40_CHARACTER_SOURCECOMMIT_SHA" `
  -Helm "C:\Tools\helm\helm.exe"
```

The script rejects a revision that does not equal SourceCommit `master`, then
performs an atomic Helm rollout. Kubernetes pulls through the authenticated
registry public endpoint. Local Docker is not used.

## Pipeline stage after the first cloud build

Once both projects are proven independently, create a SourcePipeline triggered
by SourceCommit `master`:

1. SourceCommit trigger (`architect_report/master`).
2. Runtime SourceBuild project; tests and runtime image.
3. Migration SourceBuild project.
4. Controlled deployment stage.

SourceDeploy requires plain Kubernetes manifests stored in SourceCommit. The
current production-safe migration flow is a Helm pre-rollout Job, so the first
cloud-build stage deliberately keeps deployment as the small, build-free Helm
command above. Move deployment to SourceDeploy only after providing an
equivalent one-time migration mechanism; do not run schema migration from every
application pod.
