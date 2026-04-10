#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALLER="$ROOT/auplc-installer"

grep -q 'verify_sha256()' "$INSTALLER"
grep -q 'HELM_LINUX_AMD64_SHA256=' "$INSTALLER"
grep -q 'K9S_LINUX_AMD64_DEB_SHA256=' "$INSTALLER"
grep -q 'K3S_INSTALLER_SHA256=' "$INSTALLER"
grep -q 'ROCM_DEVICE_PLUGIN_SHA256=' "$INSTALLER"
grep -q 'INSTALL_K3S_VERSION="${K3S_VERSION}"' "$INSTALLER"

if grep -q 'curl -sfL https://get.k3s.io |' "$INSTALLER"; then
    echo 'FAIL: k3s still uses pipe-to-shell'
    exit 1
fi

if grep -q 'kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml' "$INSTALLER"; then
    echo 'FAIL: ROCm plugin still applies remote URL directly'
    exit 1
fi

grep -q 'verify_sha256 /tmp/helm-linux-amd64.tar.gz' "$INSTALLER"
grep -q 'verify_sha256 /tmp/k9s_linux_amd64.deb' "$INSTALLER"
grep -q 'verify_sha256 /tmp/get-k3s.sh' "$INSTALLER"
grep -q 'verify_sha256 /tmp/k8s-ds-amdgpu-dp.yaml' "$INSTALLER"

echo 'Installer integrity checks present.'
