# NCP Pilot deployment runbook

This runbook deploys the current report portal to a one-node NKS pilot. It
keeps Public and GOV workers logically separated and keeps all credentials out
of Git. Run commands from the repository root.

## 0. Responsibility split

The source package already defines:

- separate web, scheduler, Public worker and GOV worker deployments;
- a PostgreSQL StatefulSet for the pilot;
- an idempotent database migration Job;
- retained Block Storage classes and PVCs;
- an ALB Ingress with TLS 1.2 minimum;
- a local PostgreSQL backup CronJob;
- readiness, liveness and schema-wait checks.

The NCP administrator creates the VPC, subnets, NKS cluster, registry,
certificate and DNS records. Do not enter customer credentials in the NCP
console until the namespace and Kubernetes Secrets are ready.

## 1. Create the NCP infrastructure

Create these resources in the same region and VPC:

1. A VPC, for example `10.20.0.0/16`.
2. An NKS worker subnet, for example `10.20.10.0/24`.
3. A dedicated public Load Balancer subnet, for example `10.20.20.0/24`.
4. Outbound routing for NCP APIs and the configured SMTP server. A private
   worker subnet normally needs a NAT Gateway.
5. A KVM NKS Single Zone cluster with one 4 vCPU/8 GiB worker for the pilot.
6. An Object Storage bucket and a private Container Registry.

Register the public Load Balancer subnet in the NKS cluster. KVM clusters
include the ALB Ingress Controller; verify it after kubeconfig is configured:

```sh
kubectl get nodes
kubectl get pods -n kube-system -l app.kubernetes.io/name=alb-ingress-controller
kubectl get storageclass nks-block-storage
```

The NKS default Block Storage class has `reclaimPolicy: Delete`. This chart
creates `ncp-report-retain` with `Retain` instead. NCP Block Storage accepts
ReadWriteOnce volumes in 10 GiB increments, so the pilot uses 20 GiB volumes.

Official references:

- [NKS getting started](https://guide.ncloud-docs.com/docs/k8s-k8sstart)
- [NKS ALB Ingress configuration](https://guide.ncloud-docs.com/release-20260423/docs/en/k8s-k8suse-albingress)
- [NKS Block Storage CSI](https://guide.ncloud-docs.com/docs/en/k8s-k8suse-bscsi)
- [Container Registry overview](https://guide.ncloud-docs.com/docs/containerregistry-overview)

## 2. Set local deployment values

Copy the pilot values file. The destination is ignored by Git.

```sh
cp deploy/helm/ncp-report/values-pilot.yaml \
  deploy/helm/ncp-report/values-local.yaml
```

Replace these values in `values-local.yaml`:

```yaml
image:
  repository: your-registry.kr.ncr.ntruss.com/ncp-report
  tag: pilot-001
migration:
  image:
    repository: your-registry.kr.ncr.ntruss.com/ncp-report-migrate
    tag: pilot-001
ingress:
  enabled: false
  host: report.your-domain.example
  certificateNo: ""
```

Keep Ingress disabled until the web portal passes the port-forward test.

## 3. Build and push the two images

Use a versioned immutable tag. Do not put secrets in Docker build arguments.

```sh
docker build --target runtime \
  -t your-registry.kr.ncr.ntruss.com/ncp-report:pilot-001 .
docker build --target migration \
  -t your-registry.kr.ncr.ntruss.com/ncp-report-migrate:pilot-001 .
docker push your-registry.kr.ncr.ntruss.com/ncp-report:pilot-001
docker push your-registry.kr.ncr.ntruss.com/ncp-report-migrate:pilot-001
```

Use a least-privilege registry credential for the cluster. Create its image
pull Secret without saving the rendered Secret to Git:

```sh
kubectl create namespace ncp-report
kubectl -n ncp-report create secret docker-registry ncp-registry \
  --docker-server=your-registry.kr.ncr.ntruss.com \
  --docker-username="$NCR_ACCESS_KEY" \
  --docker-password="$NCR_SECRET_KEY"
```

Avoid placing the access and secret keys literally in shell commands or shell
history.

## 4. Create application secrets

Copy the example file and generate new random values:

```sh
cp deploy/private/.env.k8s.example deploy/private/.env.k8s
```

For a new pilot, create a 32-byte encryption key. For a migration from the
local service, copy the existing `secrets/credential-master-key` unchanged;
otherwise existing customer API credentials cannot be decrypted.

```sh
mkdir -p deploy/private
openssl rand -base64 32 > deploy/private/credential-master-key
```

Populate `.env.k8s`, then apply the Secret:

```sh
sh deploy/scripts/create-kubernetes-secrets.sh
```

On Windows PowerShell:

```powershell
.\deploy\scripts\create-kubernetes-secrets.ps1
```

Back up the credential master key offline. Losing it makes encrypted customer
API credentials unrecoverable. Kubernetes Secrets are not a replacement for
KMS; migrate the encryption provider to KMS or Secret Manager before the full
production launch.

## 5. Validate and install the chart

Install Helm 3 locally, then validate the package:

```sh
sh deploy/scripts/verify-chart.sh
```

Install the pilot:

```sh
helm upgrade --install ncp-report deploy/helm/ncp-report \
  --namespace ncp-report --create-namespace \
  --values deploy/helm/ncp-report/values-local.yaml \
  --wait --wait-for-jobs --timeout 15m
```

The app containers wait for schema version `180`. The migration Job is created
with the other resources, connects as the DB administrator, creates the
application roles and applies all SQL files in filename order. This avoids a
first-install deadlock between a post-install hook and `helm --wait`.

```sh
kubectl -n ncp-report get pods,pvc,jobs
kubectl -n ncp-report logs -l app.kubernetes.io/component=migration
kubectl -n ncp-report rollout status deployment/ncp-report-web
```

## 6. Verify the portal before creating the ALB

```sh
kubectl -n ncp-report port-forward \
  service/ncp-report-web 8080:80
```

Open `http://127.0.0.1:8080`, then verify:

1. MSP login and customer/user lists.
2. Customer API credential registration and masked redisplay.
3. One Public and one GOV report job.
4. Report history and snapshot replay.
5. Daily/monthly/custom time schedules.
6. NAVER WORKS SMTP egress if email is enabled.

## 7. Enable HTTPS

Register the domain certificate in NCP Certificate Manager. Get its numeric
certificate number from the Resource Manager NRN, then update the private
values file:

```yaml
ingress:
  enabled: true
  host: report.your-domain.example
  certificateNo: "123456"
```

Apply it:

```sh
helm upgrade ncp-report deploy/helm/ncp-report \
  --namespace ncp-report \
  --values deploy/helm/ncp-report/values-local.yaml \
  --wait --wait-for-jobs --timeout 15m
kubectl -n ncp-report get ingress
```

The chart exposes HTTP and HTTPS, redirects HTTP to HTTPS, enables HTTP/2 and
sets the minimum protocol to TLS 1.2. Point the domain DNS record to the ALB
address after the Ingress obtains an address.

## 8. Backups and known pilot limitations

The included CronJob creates a daily custom-format `pg_dump` on a retained
backup PVC at 03:00 KST and keeps seven days. Check it manually:

```sh
kubectl -n ncp-report create job --from=cronjob/ncp-report-database-backup backup-test
kubectl -n ncp-report logs job/backup-test
```

This protects against a PostgreSQL data-volume failure but not a cluster or
account-wide loss. Before accepting production data, upload encrypted backups
to Object Storage and test a restore.

The artifact PVC is ReadWriteOnce and is suitable only for the one-node pilot.
Production values disable it. Production should store HTML/PDF artifacts in
Object Storage while PostgreSQL remains the report replay source.

## 9. Automated deployment after the pilot works

Do not enable continuous deployment before the manual installation and restore
test pass. Then create this pipeline:

```text
SourceCommit push
  -> SourceBuild tests and two image builds
  -> Container Registry push
  -> SourceDeploy migration
  -> SourceDeploy application workloads
```

SourceDeploy requires NKS manifest files in SourceCommit, so the automated
deployment phase should render this Helm chart to
`deploy/sourcedeploy/rendered/` with the build's immutable image tag. Do not
register manually applied objects and SourceDeploy-managed objects under the
same Kubernetes names until ownership is deliberately transferred.

- [SourceBuild start](https://guide.ncloud-docs.com/docs/en/sourcebuild-start)
- [SourceDeploy NKS scenarios](https://guide.ncloud-docs.com/docs/en/sourcedeploy-use-scenario)

Add this automation only after the actual registry endpoint, NKS namespace and
SourceCommit repository are known.
