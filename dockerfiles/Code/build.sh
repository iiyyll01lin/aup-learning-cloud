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
EXTENSION_DIR="${SCRIPT_DIR}/auplc-hub-link"
EXTENSION_VSIX="${EXTENSION_DIR}/auplc-hub-link-0.0.0.vsix"

npm --prefix "${EXTENSION_DIR}" ci
rm -f "${EXTENSION_VSIX}"
npm --prefix "${EXTENSION_DIR}" run package
test -f "${EXTENSION_VSIX}"

docker build \
  -f "${SCRIPT_DIR}/Dockerfile" \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  --build-arg "IMAGE_FLAVOR=${IMAGE_FLAVOR}" \
  -t "${IMAGE_TAG}" \
  "${SCRIPT_DIR}"
