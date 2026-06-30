#!/usr/bin/env bash
# One-click setup + demo bootstrap for AUP Learning Cloud on a Strix Halo (gfx1151) Ubuntu box.
#
# Env flags: ADMIN=1 (default) grants the auto-login user 'student' JupyterHub admin rights
#            (so http://localhost:30890/hub/admin works); set ADMIN=0 to opt out.
#            APU=1/0 force/skip the Ryzen AI OEM-kernel step (default: auto-detect;
#            Radeon dGPUs use the stock Ubuntu kernel and skip it).
#            STRICT=1 aborts if any prerequisite check fails; SKIP_CHECKS=1 skips them.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/AMDResearch/aup-learning-cloud.git}"
IMAGE_TAG="${IMAGE_TAG:-develop}"
ADMIN="${ADMIN:-1}"
OEM_KERNEL_PKG="${OEM_KERNEL_PKG:-linux-image-6.14.0-1018-oem}"
# Kernel release string (uname -r form) implied by OEM_KERNEL_PKG, e.g.
# linux-image-6.14.0-1018-oem -> 6.14.0-1018-oem. Used to decide whether the
# box is already running the required OEM kernel.
OEM_KERNEL_REL="${OEM_KERNEL_PKG#linux-image-}"
STATE_DIR="/var/lib/auplc-demo"
STATE_FILE="$STATE_DIR/state"
REBOOT_FILE="$STATE_DIR/reboots"
LOG="/var/log/auplc-demo-setup.log"
RESUME_UNIT="auplc-demo-resume.service"

# --- escalate to root (keeps SUDO_USER so kubeconfig lands in the real user's home) ---
if [ "$(id -u)" -ne 0 ]; then exec sudo -E IMAGE_TAG="$IMAGE_TAG" ADMIN="$ADMIN" OEM_KERNEL_PKG="$OEM_KERNEL_PKG" REPO_URL="$REPO_URL" bash "$0" "$@"; fi

SELF="$(readlink -f "$0")"
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"; REAL_HOME="${REAL_HOME:-/root}"
mkdir -p "$STATE_DIR"; exec > >(tee -a "$LOG") 2>&1
echo "== auplc demo setup ($(date)) user=$REAL_USER tag=$IMAGE_TAG mode=${1:-auto} =="

# On any unhandled failure, surface where to look (reboot paths exit 0, so this
# only fires on real errors).
trap 'rc=$?; [ "$rc" -ne 0 ] && echo "ERROR: setup failed (exit $rc). Full log: $LOG"; exit $rc' ERR

# --- single-instance lock: if another run is already going (e.g. a manual run
#     while the post-reboot auto-resume is still installing), exit instead of
#     kicking off a second concurrent install ---
exec 9>"$STATE_DIR/lock"
if ! flock -n 9; then
  echo "Another demo-setup.sh run is already in progress (lock: $STATE_DIR/lock). Exiting."
  exit 0
fi

MODE="prereq"
[ "${1:-}" = "--resume" ] && MODE="install"
[ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "await-install" ] && MODE="install"

# Pin GRUB's default boot entry to a specific kernel release so a newer-but-
# unsupported kernel (e.g. >6.14) cannot win the default slot and leave us off
# the required OEM kernel after reboot. Best-effort: never fatal.
force_default_kernel() {
  local rel="$1" grubcfg=/boot/grub/grub.cfg gd=/etc/default/grub
  [ -f "$grubcfg" ] || { echo "WARN: $grubcfg not found; cannot pin GRUB default to $rel."; return 0; }

  # menuentry_id_option of the target kernel's normal (non-recovery) entry.
  local entry
  entry="$(grep -E "menuentry .*'gnulinux-${rel}-[^']*'" "$grubcfg" \
            | grep -v recovery \
            | sed -n "s/.*\$menuentry_id_option '\([^']*\)'.*/\1/p" | head -n1 || true)"
  if [ -z "$entry" ]; then
    echo "WARN: no GRUB menuentry found for kernel $rel; leaving GRUB default unchanged."
    return 0
  fi

  # Optional "Advanced options for Ubuntu" submenu wrapper id.
  local submenu
  submenu="$(sed -n "s/^submenu '[^']*' \$menuentry_id_option '\([^']*\)'.*/\1/p" "$grubcfg" | head -n1 || true)"
  local target="$entry"; [ -n "$submenu" ] && target="${submenu}>${entry}"

  if grep -q '^GRUB_DEFAULT=' "$gd" 2>/dev/null; then
    sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=saved/' "$gd" || true
  else
    echo 'GRUB_DEFAULT=saved' >> "$gd" || true
  fi
  update-grub >/dev/null 2>&1 || true
  grub-set-default "$target" 2>/dev/null \
    || grub-editenv - set saved_entry="$target" 2>/dev/null || true
  echo "Pinned GRUB default to kernel $rel."
}

# Verify the documented prerequisites (Ubuntu 24.04, x86_64, 32GB+ RAM, 500GB+
# disk, an AMD GPU). Soft by default: warn and continue. STRICT=1 aborts on any
# failure; SKIP_CHECKS=1 skips the whole block.
preflight_checks() {
  [ "${SKIP_CHECKS:-0}" = "1" ] && { echo "SKIP_CHECKS=1: skipping prerequisite checks."; return 0; }
  local fails=0
  warn() { echo "  ✗ $1"; fails=$((fails + 1)); }
  okk()  { echo "  ✓ $1"; }
  echo "-- Preflight checks (STRICT=1 to enforce, SKIP_CHECKS=1 to skip) --"

  # OS: Ubuntu 24.04
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    if [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ]; then
      okk "OS ${PRETTY_NAME:-Ubuntu 24.04}"
    else
      warn "OS is ${PRETTY_NAME:-unknown}; expected Ubuntu 24.04 LTS"
    fi
  else
    warn "/etc/os-release missing; cannot verify Ubuntu 24.04"
  fi

  # CPU architecture
  local arch; arch="$(uname -m)"
  [ "$arch" = "x86_64" ] && okk "arch $arch" || warn "arch $arch; expected x86_64"

  # RAM >= 32GB (64GB recommended)
  local kb gib; kb="$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 0)"; gib=$((kb / 1024 / 1024))
  [ "$gib" -ge 30 ] && okk "RAM ${gib}GiB" || warn "RAM ${gib}GiB; need 32GB+ (64GB recommended)"

  # Free disk on /var/lib (k3s + docker + images live there) >= 500GB
  local fg; fg="$(df -BG --output=avail /var/lib 2>/dev/null | tail -n1 | tr -dc '0-9' || true)"; fg="${fg:-0}"
  [ "$fg" -ge 500 ] && okk "disk ${fg}GB free on /var/lib" || warn "only ${fg}GB free on /var/lib; need 500GB+"

  # AMD GPU presence + supported generation (Ryzen AI 300+ APU / Radeon 9000+ dGPU)
  if command -v lspci >/dev/null 2>&1; then
    local gpus; gpus="$(lspci -nn 2>/dev/null | grep -Ei 'vga|display|3d controller' | grep -Ei 'amd|ati' || true)"
    if [ -n "$gpus" ]; then
      okk "AMD GPU detected"
      echo "$gpus" | grep -qiE '780M|880M|890M|8060S|9070|r9700|9600 gre|strix|phoenix|navi 4' \
        && okk "supported AMD GPU class" || warn "GPU may be unsupported (need Ryzen AI 300+ or Radeon 9000+)"
    else
      warn "no AMD GPU detected via lspci"
    fi
  else
    echo "  ? lspci unavailable; skipping GPU presence check"
  fi

  # Internet reachability (git clone, get.docker.com, image pulls)
  if curl -fsI --max-time 8 https://github.com >/dev/null 2>&1; then
    okk "internet reachable"
  else
    warn "no internet to github.com (need GitHub/Docker/registry access)"
  fi

  # Secure Boot: OEM-kernel modules may need MOK signing
  if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi enabled; then
    echo "  ! Secure Boot enabled: the OEM kernel may need module signing / MOK enrolment."
  fi

  if [ "$fails" -gt 0 ]; then
    echo "Preflight: $fails issue(s) found."
    [ "${STRICT:-0}" = "1" ] && { echo "STRICT=1: aborting."; exit 1; }
    echo "Continuing anyway (fix the above, or set STRICT=1 to enforce)."
  else
    echo "Preflight: all checks passed."
  fi
  return 0
}

# Only Ryzen AI APUs (integrated GPU) need the OEM kernel; Radeon dGPUs run fine
# on the stock Ubuntu kernel. Override with APU=1 (force) or APU=0 (skip);
# default auto-detects via lspci and assumes APU when uncertain (the script's
# primary target). Best-effort: never fatal.
is_apu() {
  case "${APU:-auto}" in
    1) return 0 ;;
    0) return 1 ;;
  esac
  if command -v lspci >/dev/null 2>&1; then
    local amd_gpus
    amd_gpus="$(lspci -nn 2>/dev/null | grep -Ei 'vga|display|3d controller' | grep -Ei 'amd|ati' || true)"
    # A discrete Radeon RX / RDNA4 card means dGPU → stock kernel is fine.
    echo "$amd_gpus" | grep -qiE 'radeon rx|r9700|9600 gre|navi 4' && return 1
    [ -n "$amd_gpus" ] && return 0
  fi
  return 0
}

# --- locate the repo (use the one beside this script, else clone into the user's home) ---
if [ -x "$(dirname "$SELF")/auplc-installer" ]; then
  REPO_DIR="$(dirname "$SELF")"
else
  REPO_DIR="$REAL_HOME/aup-learning-cloud"
  if [ ! -x "$REPO_DIR/auplc-installer" ]; then
    sudo -u "$REAL_USER" git clone "$REPO_URL" "$REPO_DIR"
  fi
fi

if [ "$MODE" = "prereq" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y build-essential wget curl git ca-certificates pciutils \
                     python3-questionary python3-prompt-toolkit
  command -v docker >/dev/null 2>&1 || curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$REAL_USER" || true

  preflight_checks
  if ! is_apu; then
    echo "Radeon dGPU detected (or APU=0); stock Ubuntu kernel is fine — skipping OEM kernel install + reboot."
  elif [ "$(uname -r)" = "$OEM_KERNEL_REL" ]; then
    echo "Ryzen AI APU already on required OEM kernel ($OEM_KERNEL_REL); skipping kernel install + reboot."
  else
    echo "Ryzen AI APU running $(uname -r) != required $OEM_KERNEL_REL; force-installing OEM kernel ($OEM_KERNEL_PKG)."
    n="$(cat "$REBOOT_FILE" 2>/dev/null || echo 0)"; n=$((n + 1)); echo "$n" > "$REBOOT_FILE"
    if [ "$n" -gt 2 ]; then
      echo "ERROR: rebooted $n times and still not on $OEM_KERNEL_REL; aborting to avoid a loop. Check GRUB/Secure Boot."; exit 1
    fi
    apt-cache show "$OEM_KERNEL_PKG" >/dev/null 2>&1 \
      || { echo "ERROR: $OEM_KERNEL_PKG not available in apt sources; set OEM_KERNEL_PKG=... or APU=0."; exit 1; }
    apt-get install -y "$OEM_KERNEL_PKG"
    force_default_kernel "$OEM_KERNEL_REL"
    echo "await-install" > "$STATE_FILE"
    cat >/etc/systemd/system/$RESUME_UNIT <<EOF
[Unit]
Description=Resume AUP Learning Cloud demo install after reboot
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=IMAGE_TAG=$IMAGE_TAG
Environment=ADMIN=$ADMIN
ExecStart=/usr/bin/env SUDO_USER=$REAL_USER /bin/bash $SELF --resume

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable "$RESUME_UNIT"
    echo "OEM kernel installed and pinned as GRUB default. Rebooting; install will continue automatically."
    echo "Watch: sudo journalctl -u $RESUME_UNIT -f   (or tail -f $LOG)"
    sleep 3; reboot; exit 0
  fi
fi

# --- install phase (fresh, or auto-resumed after reboot) ---
echo "await-install" > "$STATE_FILE"
# Soft check: confirm the reboot actually landed on the required OEM kernel.
if is_apu && [ "$(uname -r)" != "$OEM_KERNEL_REL" ]; then
  echo "WARN: running $(uname -r), not the required $OEM_KERNEL_REL — GPU may not work. Check GRUB default."
fi
export SUDO_USER="$REAL_USER"
cd "$REPO_DIR"
# -v gives linear logs (nicer under systemd/journald than the progress-bar UI)
./auplc-installer install -y --image-tag="$IMAGE_TAG" -v

if [ "$ADMIN" = "1" ]; then
  echo "ADMIN=1: granting 'student' JupyterHub admin (helm upgrade)..."
  ADMIN_VALUES="$STATE_DIR/admin.yaml"
  cat > "$ADMIN_VALUES" <<'YAML'
hub:
  config:
    Authenticator:
      admin_users:
        - student
YAML
  export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
  HELM_ARGS=( -f "$REPO_DIR/runtime/values.yaml" )
  [ -f "$REPO_DIR/runtime/values.local.yaml" ] && HELM_ARGS+=( -f "$REPO_DIR/runtime/values.local.yaml" )
  HELM_ARGS+=( -f "$ADMIN_VALUES" )
  if helm upgrade jupyterhub "$REPO_DIR/runtime/chart" --namespace jupyterhub "${HELM_ARGS[@]}"; then
    kubectl -n jupyterhub rollout status deployment/hub --timeout=300s || true
    echo "Admin UI enabled for 'student'."
  else
    echo "WARN: admin helm upgrade failed; demo still works, but /hub/admin will be 403 for 'student'."
  fi
fi

systemctl disable "$RESUME_UNIT" 2>/dev/null || true
rm -f "/etc/systemd/system/$RESUME_UNIT"; systemctl daemon-reload 2>/dev/null || true
rm -f "$STATE_FILE" "$REBOOT_FILE"

# Post-install health check: is the Hub actually serving?
if curl -fsS --max-time 10 http://localhost:30890/hub/api >/dev/null 2>&1; then
  echo "Health check: JupyterHub API is responding."
else
  echo "WARN: JupyterHub API not responding yet on :30890; give pods a minute (kubectl -n jupyterhub get pods)."
fi
echo ""
echo "DONE. Open the demo in a browser:  http://localhost:30890  (auto-login as 'student')"
echo "Remote: http://<this-host-ip>:30890   |  Admin: http://localhost:30890/hub/admin"
[ "$ADMIN" = "1" ] && echo "Admin UI:  http://localhost:30890/hub/admin   (you are 'student', now an admin)"
