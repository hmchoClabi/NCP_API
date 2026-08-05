#!/bin/sh
set -eu

registry="${1:-architect-ncp-report.kr.ncr.ntruss.com}"
tag="${2:-pilot-20260804-001}"

case "$registry" in
    ""|*[!a-z0-9.-]*)
        echo "Registry contains unsupported characters." >&2
        exit 2
        ;;
    *.ncr.ntruss.com) ;;
    *)
        echo "Registry must be an NCP Container Registry public endpoint." >&2
        exit 2
        ;;
esac

case "$tag" in
    ""|*[!A-Za-z0-9_.-]*)
        echo "Tag is not a valid container image tag." >&2
        exit 2
        ;;
esac

runtime_image="${registry}/ncp-report:${tag}"
migration_image="${registry}/ncp-report-migrate:${tag}"

docker build --target runtime --tag "$runtime_image" .
docker build --target migration --tag "$migration_image" .
docker push "$runtime_image"
docker push "$migration_image"

echo "Published both images with immutable tag $tag."
