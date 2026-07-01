#!/usr/bin/env bash
# auplc-gpu-doctor.sh - diagnose & fix AMD GPU driver mismatches that break ROCm
#   on AUP Learning Cloud nodes (especially brand-new APUs like Strix Halo / gfx1151).
#
#   sudo ./auplc-gpu-doctor.sh           # diagnose only (read-only)
#   sudo ./auplc-gpu-doctor.sh --smoke   # diagnose + run a GPU compute smoke test (docker)
#   sudo ./auplc-gpu-doctor.sh --fix     # diagnose, then upgrade amdgpu-dkms to the required
#                                        # release and rebuild DKMS (reboot afterwards)
#
# Why this exists: the host amdgpu kernel/DKMS driver must keep up with the ROCm
# userspace shipped inside the course containers. On gfx1151 an older driver
# (e.g. amdgpu 30.30) cannot initialise the command processor, so every GPU
# submission triggers an "amdgpu [gfxhub] page fault" and notebooks crash even on
# a trivial torch op. Bumping the driver to the baseline (31.30) fixes it.
#
# NOTE: keep REQUIRED_RELEASE / AMDGPU_INSTALL_DEB in sync with
#       deploy/ansible/roles/rocm/tasks/main.yml
set -uo pipefail   # intentionally NOT -e: run every check even if some fail

# --- Required AMD GPU driver baseline -------------------------------------
REQUIRED_RELEASE="31.30"
AMDGPU_INSTALL_DEB="https://repo.radeon.com/amdgpu-install/31.30/ubuntu/noble/amdgpu-install_31.30.313000-1_all.deb"

MODE="check"
RUN_SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --fix)   MODE="fix" ;;
    --check) MODE="check" ;;
    --smoke) RUN_SMOKE=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg (use --check | --fix | --smoke)"; exit 2 ;;
  esac
done

# dmesg/journalctl and --fix all need root.
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi

ok(){   echo "  [OK]   $*"; }
warn(){ echo "  [WARN] $*"; }
bad(){  echo "  [FAIL] $*"; }
act(){  echo "  [FIX]  $*"; }
info(){ echo "  [..]   $*"; }

# "31.30" -> 3130 ; non-numeric -> 0
rel_to_num(){
  echo "${1:-0}" | awk -F. '
    NF>=2 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ {printf "%d", $1*100+$2; found=1}
    END {if (!found) print 0}'
}

REQUIRED_NUM="$(rel_to_num "$REQUIRED_RELEASE")"

# Best-effort GPU identity (gfx target + marketing name).
detect_gpu(){
  local gfx="" name=""
  if command -v rocminfo >/dev/null 2>&1; then
    gfx="$(rocminfo 2>/dev/null | grep -oE 'gfx[0-9a-f]{3,4}' | head -n1)"
  fi
  name="$(cat /sys/class/drm/card*/device/product_name 2>/dev/null | head -n1)"
  echo "${gfx:-unknown} | ${name:-unknown}"
}

# Installed amdgpu release, e.g. "31.30". Prefer the amdgpu-install package
# version, fall back to the configured apt source path.
installed_release(){
  local v rel
  v="$(dpkg-query -W -f='${Version}' amdgpu-install 2>/dev/null || true)"
  if [ -n "$v" ]; then
    rel="$(echo "$v" | cut -d: -f2- | cut -d. -f1,2)"   # 31.30.0.0... -> 31.30
    [ -n "$rel" ] && { echo "$rel"; return; }
  fi
  rel="$(grep -rhoE 'amdgpu/[0-9]+\.[0-9]+' /etc/apt/sources.list.d/ 2>/dev/null \
          | grep -oE '[0-9]+\.[0-9]+' | sort -V | tail -n1)"
  echo "${rel:-unknown}"
}

# Run a real GPU compute kernel inside a cached course image (non-destructive:
# uses a timestamp marker instead of clearing the kernel ring buffer).
smoke_gpu(){
  command -v docker >/dev/null 2>&1 || { warn "docker not found; skipping smoke test"; return; }
  local img rgid t0 out
  img="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
          | grep -E 'amdresearch/auplc-(base|cv|dl|llm|physim).*gfx' | head -n1)"
  [ -z "$img" ] && img="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
          | grep -E 'amdresearch/auplc-base' | head -n1)"
  [ -z "$img" ] && { warn "no local auplc GPU image found; skipping smoke test"; return; }
  info "smoke image: $img"
  rgid="$(getent group render 2>/dev/null | cut -d: -f3)"
  t0="$(date '+%Y-%m-%d %H:%M:%S')"
  out="$(docker run --rm --device=/dev/kfd --device=/dev/dri \
          --group-add video ${rgid:+--group-add "$rgid"} \
          --security-opt seccomp=unconfined "$img" \
          python3 -c "import torch; print('cuda', torch.cuda.is_available()); print(torch.ones(8, device='cuda').sum())" 2>&1)"
  if echo "$out" | grep -q 'tensor(8'; then
    if dmesg -T --since "$t0" 2>/dev/null | grep -qiE 'amdgpu.*page fault'; then
      bad "smoke test computed but a GPU page fault appeared (driver still bad)"
    else
      ok "GPU compute smoke test passed (torch.ones(8) on GPU, no page fault)"
    fi
  else
    bad "GPU compute smoke test FAILED (torch could not run on GPU):"
    echo "$out" | sed 's/^/         /'
  fi
}

echo "== AUPLC GPU driver doctor ($(date)) mode=$MODE =="
echo "--- Diagnosis ---"
info "kernel: $(uname -r)"
info "GPU:    $(detect_gpu)"

REL="$(installed_release)"
REL_NUM="$(rel_to_num "$REL")"
SYS_VER="$(cat /sys/module/amdgpu/version 2>/dev/null || echo 'n/a')"
info "amdgpu release: ${REL} (module ${SYS_VER}); required >= ${REQUIRED_RELEASE}"

NEED_FIX=0

# DKMS module present for the RUNNING kernel? Use `dkms status` (no positional
# arg, which some DKMS versions reject) and match the running kernel, so a
# just-rebooted, mid-autoinstall state is reported accurately instead of a
# blanket "not installed" false alarm.
if command -v dkms >/dev/null 2>&1; then
  krel="$(uname -r)"
  dkms_amdgpu="$(dkms status 2>/dev/null | grep -i amdgpu)"
  if printf '%s\n' "$dkms_amdgpu" | grep -F "$krel" | grep -qi installed; then
    ok "amdgpu DKMS module installed for $krel"
  elif printf '%s\n' "$dkms_amdgpu" | grep -qi installed; then
    warn "amdgpu DKMS installed, but not yet for running kernel $krel (autoinstall may still be building)"
  else
    warn "amdgpu DKMS module not reported as installed (check: dkms status)"
  fi
fi

# Driver release vs required baseline.
if [ "${REL_NUM:-0}" -ge "$REQUIRED_NUM" ] 2>/dev/null; then
  ok "amdgpu release ${REL} meets baseline ${REQUIRED_RELEASE}"
else
  bad "amdgpu release ${REL} is BELOW required ${REQUIRED_RELEASE} (known gfx1151 page-fault cause)"
  NEED_FIX=1
fi

# Any GPU page fault already in the ring buffer?
if dmesg 2>/dev/null | grep -qiE 'amdgpu.*page fault|GCVM_L2_PROTECTION_FAULT'; then
  bad "GPU page fault present in current dmesg (amdgpu)"
  NEED_FIX=1
else
  ok "no amdgpu page fault in current dmesg"
fi

if [ "$RUN_SMOKE" = 1 ]; then
  echo "--- GPU compute smoke test ---"
  smoke_gpu
fi

echo "--- Verdict ---"
if [ "$NEED_FIX" = 0 ]; then
  ok "GPU driver stack looks healthy (release ${REL} >= ${REQUIRED_RELEASE})."
  [ "$MODE" = "fix" ] && info "Nothing to fix."
  exit 0
fi

if [ "$MODE" != "fix" ]; then
  warn "Issue(s) found. Re-run with --fix to upgrade amdgpu to ${REQUIRED_RELEASE} and rebuild DKMS:"
  echo "         sudo $0 --fix"
  exit 1
fi

echo "--- Applying fix: upgrade amdgpu to ${REQUIRED_RELEASE} ---"
export DEBIAN_FRONTEND=noninteractive

act "installing build headers for $(uname -r)"
apt-get install -y "linux-headers-$(uname -r)" >/dev/null 2>&1 \
  || warn "could not install linux-headers-$(uname -r) (may already be present)"

act "switching amdgpu repo to ${REQUIRED_RELEASE}"
tmp="$(mktemp --suffix=.deb)"
if curl -fsSL "$AMDGPU_INSTALL_DEB" -o "$tmp"; then
  # --force-confold keeps your existing apt source files (e.g. rocm.list) on conflict.
  apt-get install -y -o Dpkg::Options::=--force-confold "$tmp" \
    || { bad "amdgpu-install ${REQUIRED_RELEASE} failed to install"; rm -f "$tmp"; exit 1; }
else
  bad "failed to download $AMDGPU_INSTALL_DEB"; rm -f "$tmp"; exit 1
fi
rm -f "$tmp"

apt-get update -y
act "upgrading amdgpu-dkms + firmware"
apt-get install -y -o Dpkg::Options::=--force-confold amdgpu-dkms amdgpu-dkms-firmware \
  || { bad "amdgpu-dkms upgrade failed"; exit 1; }

NEW_REL="$(installed_release)"
if dkms status amdgpu 2>/dev/null | grep -q "installed"; then
  ok "amdgpu-dkms now ${NEW_REL}; DKMS module built"
else
  warn "amdgpu-dkms now ${NEW_REL} but DKMS build not confirmed (check: dkms status amdgpu)"
fi

echo ""
echo "DONE. Reboot to load the new driver, then verify:"
echo "    sudo reboot"
echo "    sudo $0 --check     # expect: amdgpu release ${REQUIRED_RELEASE} ... [OK]"
echo "    sudo $0 --smoke     # GPU compute smoke test"
