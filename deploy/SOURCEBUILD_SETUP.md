# NCP cloud build setup

Local Docker builds are disabled for normal releases. NCP SourceBuild builds
two least-privilege images from the `architect_report` SourceCommit `main`
branch. SourceBuild uploads both images to `architect-ncp-report` Container
Registry; the deployment script only updates NKS to the resulting tags.

## Project 1: application runtime

Create a SourceBuild project with these values:

| Field | Value |
| --- | --- |
| Project name | `architect-report-runtime` |
| Build target | SourceCommit |
| Repository | `architect_report` |
| Branch | `main` |
| Build environment | SourceBuild-managed Python 3.13 on Ubuntu 20.04 |
| Docker image build | Enabled, Docker engine 20.10.18 |
| Compute | Smallest type sufficient for the pilot |
| Timeout | 20 minutes |

Build commands:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

Docker image build settings:

| Field | Value |
| --- | --- |
| Dockerfile | `Dockerfile.runtime` |
| Registry | `architect-ncp-report` |
| Image name | `ncp-report` |
| Image tag | `build-#` |
| Set latest | Enabled |

Do not enable "upload completed build environment image". That option is not
the Dockerfile image and can retain build-server state.

## Project 2: database migration

Create a second project:

| Field | Value |
| --- | --- |
| Project name | `architect-report-migration` |
| Build target | SourceCommit `architect_report`, branch `main` |
| Build environment | SourceBuild-managed base image on Ubuntu 20.04 |
| Docker image build | Enabled, Docker engine 20.10.18 |
| Dockerfile | `Dockerfile.migration` |
| Registry | `architect-ncp-report` |
| Image name | `ncp-report-migrate` |
| Image tag | `build-#` |
| Set latest | Enabled |
| Timeout | 10 minutes |

The runtime project owns tests. Configure the pipeline so the migration image
build starts only after the runtime build succeeds.

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

The script rejects a revision that does not equal SourceCommit `main`, then
performs an atomic Helm rollout. Kubernetes pulls through the registry private
endpoint. Local Docker is not used.

## Pipeline stage after the first cloud build

Once both projects are proven independently, create a SourcePipeline triggered
by SourceCommit `main`:

1. SourceCommit trigger (`architect_report/main`).
2. Runtime SourceBuild project; tests and runtime image.
3. Migration SourceBuild project.
4. Controlled deployment stage.

SourceDeploy requires plain Kubernetes manifests stored in SourceCommit. The
current production-safe migration flow is a Helm pre-rollout Job, so the first
cloud-build stage deliberately keeps deployment as the small, build-free Helm
command above. Move deployment to SourceDeploy only after providing an
equivalent one-time migration mechanism; do not run schema migration from every
application pod.
