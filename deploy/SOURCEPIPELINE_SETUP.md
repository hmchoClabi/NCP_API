# NCP SourcePipeline automatic NKS deployment

This deployment path keeps long-lived NCP API keys out of SourceBuild. NCP
SourcePipeline connects SourceCommit, SourceBuild and SourceDeploy. SourceDeploy
resolves the `latest` image in the committed manifest to an immutable registry
digest before applying it to NKS.

## Committed deployment manifest

SourceDeploy uses `deploy/sourcedeploy/runtime.yaml` from the
`architect_report` SourceCommit `master` branch. Regenerate it after changing
the runtime Deployment or HPA portions of the Helm chart:

```powershell
.\deploy\scripts\generate-sourcedeploy-manifest.ps1 `
  -Helm "C:\Tools\helm\helm.exe"
```

The generated manifest intentionally contains only the four application
Deployments and enabled HPAs. PostgreSQL, PVCs, Secrets, Service, Ingress,
backup jobs and database migrations remain managed by Helm. Runtime deployment
must not automatically run database migrations.

## SourceDeploy project

Create the following project in the KR VPC environment:

| Field | Value |
| --- | --- |
| Project | `architect-report-nks` |
| Stage | `pilot` |
| Target | Ncloud Kubernetes Service |
| Cluster | `architect-report-nks` |
| Namespace | `ncp-report` |

Create a Rolling deployment scenario:

| Field | Value |
| --- | --- |
| Scenario | `runtime-rolling` |
| Manifest repository | SourceCommit |
| Repository / branch | `architect_report` / `master` |
| Manifest path | `deploy/sourcedeploy/runtime.yaml` |
| Strategy | Rolling |
| Failed deployment rollback | Enabled |

The linked SourceBuild project must build `ncp-report`, publish both `build-#`
and `latest`, and use the `architect-report-build` Container Registry. The
manifest image is `${registry_endpoint}/ncp-report:latest`; SourceDeploy pins
this to the digest produced by the successful build.

## SourcePipeline project

Create one enabled pipeline named `architect-report-cicd`:

1. Source: SourceCommit `architect_report/master`.
2. Build: the successful runtime SourceBuild project.
3. Deploy: `architect-report-nks` / `pilot` / `runtime-rolling`.
4. Trigger: SourceCommit push to `master`.

Keep automatic approval disabled only for the pilot after one manual
SourceDeploy run succeeds. For production, add a deployment approval gate.

## HPA behavior

The Helm chart supports independent HPAs for web, public worker and GOV worker.
When an HPA is enabled, the target Deployment omits `spec.replicas`, so a
SourceDeploy rollout does not reset the replica count selected by the HPA.
Scheduler is deliberately excluded and remains a singleton.

CPU autoscaling requires resource requests and the Kubernetes metrics API.
They are already present in the chart, but verify the NKS metrics API before
enabling worker HPAs. Queue-depth scaling is a later enhancement; CPU is only
the safe initial signal.
