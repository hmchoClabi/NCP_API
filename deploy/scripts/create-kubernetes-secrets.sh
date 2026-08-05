#!/bin/sh
set -eu

namespace="${NAMESPACE:-ncp-report}"
secret_name="${SECRET_NAME:-ncp-report-secrets}"
env_file="${1:-deploy/private/.env.k8s}"
master_key_file="${2:-deploy/private/credential-master-key}"

if [ ! -f "$env_file" ]; then
    echo "Secret environment file not found: $env_file" >&2
    exit 2
fi
if [ ! -f "$master_key_file" ]; then
    echo "Credential master key not found: $master_key_file" >&2
    exit 2
fi

kubectl get namespace "$namespace" >/dev/null 2>&1 || kubectl create namespace "$namespace"

temporary_directory="$(mktemp -d)"
cleanup() {
    find "$temporary_directory" -type f -exec chmod u+w {} \; 2>/dev/null || true
    rm -rf -- "$temporary_directory"
}
trap cleanup EXIT HUP INT TERM
chmod 700 "$temporary_directory"

while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        ""|'#'*) continue ;;
        *=*)
            key=${line%%=*}
            value=${line#*=}
            case "$key" in
                *[!A-Za-z0-9_.-]*|"")
                    echo "Unsupported Secret key name: $key" >&2
                    exit 2
                    ;;
            esac
            printf '%s' "$value" > "$temporary_directory/$key"
            ;;
    esac
done < "$env_file"
cp "$master_key_file" "$temporary_directory/credential-master-key"

kubectl -n "$namespace" create secret generic "$secret_name" \
    --from-file="$temporary_directory" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "Secret $namespace/$secret_name is ready. Secret values were not printed."
