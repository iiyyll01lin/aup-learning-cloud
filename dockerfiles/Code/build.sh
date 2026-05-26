#!/usr/bin/env bash
set -euo pipefail

IMAGE_FLAVOR="${IMAGE_FLAVOR:-cpu}"

case "${IMAGE_FLAVOR}" in
  cpu)
    BASE_IMAGE="${BASE_IMAGE:-ghcr.io/amdresearch/auplc-default:latest}"
    IMAGE_TAG="${IMAGE_TAG:-ghcr.io/amdresearch/auplc-code-cpu:latest}"
    ;;
  gpu)
    BASE_IMAGE="${BASE_IMAGE:-ghcr.io/amdresearch/auplc-base:latest}"
    IMAGE_TAG="${IMAGE_TAG:-ghcr.io/amdresearch/auplc-code-gpu:latest}"
    ;;
  *)
    printf 'Unsupported IMAGE_FLAVOR: %s\n' "${IMAGE_FLAVOR}" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_IMAGE="${NODE_IMAGE:-docker.io/library/node:20-bookworm-slim}"
NPM_REGISTRY="${NPM_REGISTRY:-}"

docker build \
  -f "${SCRIPT_DIR}/Dockerfile" \
  --build-arg "NODE_IMAGE=${NODE_IMAGE}" \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  --build-arg "IMAGE_FLAVOR=${IMAGE_FLAVOR}" \
  --build-arg "NPM_REGISTRY=${NPM_REGISTRY}" \
  -t "${IMAGE_TAG}" \
  "${SCRIPT_DIR}"
