#!/bin/sh
set -eu

mode="${1:-migrate}"
schema_version="${2:-${REPORT_SCHEMA_VERSION:-210}}"
wait_seconds="${DB_WAIT_SECONDS:-180}"

require_value() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "Required environment variable is missing: $name" >&2
        exit 2
    fi
}

for name in PGHOST PGDATABASE PGUSER PGPASSWORD; do
    require_value "$name"
done

wait_for_database() {
    elapsed=0
    until pg_isready -q -h "$PGHOST" -p "${PGPORT:-5432}" -d "$PGDATABASE" -U "$PGUSER"; do
        if [ "$elapsed" -ge "$wait_seconds" ]; then
            echo "PostgreSQL did not become ready within ${wait_seconds}s." >&2
            exit 1
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
}

wait_for_schema() {
    elapsed=0
    until psql -X -v ON_ERROR_STOP=1 -tAc \
        "SELECT 1 FROM control.schema_versions WHERE version = '${schema_version}'" \
        2>/dev/null | grep -q '^1$'; do
        if [ "$elapsed" -ge "$wait_seconds" ]; then
            echo "Schema version ${schema_version} was not ready within ${wait_seconds}s." >&2
            exit 1
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
}

case "$mode" in
    migrate)
        wait_for_database
        for file in /schema/*.sql; do
            echo "Applying ${file##*/}"
            psql -X -v ON_ERROR_STOP=1 -f "$file"
        done
        ;;
    wait)
        wait_for_database
        wait_for_schema
        ;;
    *)
        echo "Usage: migrate.sh [migrate|wait] [schema-version]" >&2
        exit 2
        ;;
esac
