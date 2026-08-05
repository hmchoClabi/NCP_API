#!/bin/sh
set -eu

chart="deploy/helm/ncp-report"
values="$chart/values-pilot.yaml"
output="${TMPDIR:-/tmp}/ncp-report-rendered.yaml"

command -v helm >/dev/null 2>&1 || {
    echo "helm is required to validate the deployment package." >&2
    exit 2
}

helm lint "$chart" --values "$values" \
    --set image.repository=registry.example/ncp-report \
    --set image.tag=test \
    --set migration.image.repository=registry.example/ncp-report-migrate \
    --set migration.image.tag=test

helm template ncp-report "$chart" --namespace ncp-report --values "$values" \
    --set image.repository=registry.example/ncp-report \
    --set image.tag=test \
    --set migration.image.repository=registry.example/ncp-report-migrate \
    --set migration.image.tag=test > "$output"

echo "Rendered manifest: $output"
