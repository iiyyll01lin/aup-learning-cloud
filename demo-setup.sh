#!/usr/bin/env bash
# One-click setup + demo bootstrap for AUP Learning Cloud on a Strix Halo (gfx1151) Ubuntu box.
#
# Env flags: ADMIN=1 (default) grants the auto-login user 'student' JupyterHub admin rights
#            (so http://localhost:30890/hub/admin works); set ADMIN=0 to opt out.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/AMDResearch/aup-learning-cloud.git}"
IMAGE_TAG="${IMAGE_TAG:-develop}"
ADMIN="${ADMIN:-1}"
OEM_KERNEL_PKG="${OEM_KERNEL_PKG:-linux-image-6.14.0-1018-oem}"
STATE_DIR="/var/lib/auplc-demo"
STATE_FILE="$STATE_DIR/state"
LOG="/var/log/auplc-demo-setup.log"
RESUME_UNIT="auplc-demo-resume.service"

# --- escalate to root (keeps SUDO_USER so kubeconfig lands in the real user's home) ---
if [ "$(id -u)" -ne 0 ]; then exec sudo -E IMAGE_TAG="$IMAGE_TAG" ADMIN="$ADMIN" OEM_KERNEL_PKG="$OEM_KERNEL_PKG" REPO_URL="$REPO_URL" bash "$0" "$@"; fi

SELF="$(readlink -f "$0")"
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"; REAL_HOME="${REAL_HOME:-/root}"
mkdir -p "$STATE_DIR"; exec > >(tee -a "$LOG") 2>&1
echo "== auplc demo setup ($(date)) user=$REAL_USER tag=$IMAGE_TAG mode=${1:-auto} =="

MODE="prereq"
[ "${1:-}" = "--resume" ] && MODE="install"
[ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "await-install" ] && MODE="install"

gpu_ready() {
  [ -e /dev/kfd ] || return 1
  for p in /sys/class/kfd/kfd/topology/nodes/*/properties; do
    [ -f "$p" ] || continue
    v="$(awk '/^gfx_target_version/ {print $2}' "$p" 2>/dev/null || true)"
    [ -n "$v" ] && [ "$v" != "0" ] && return 0
  done
  return 1
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
  apt-get install -y build-essential wget curl git ca-certificates \
                     python3-questionary python3-prompt-toolkit
  command -v docker >/dev/null 2>&1 || curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$REAL_USER" || true

  if gpu_ready; then
    echo "GPU already visible to the kernel; skipping OEM kernel + reboot."
  else
    echo "GPU not visible yet; installing OEM kernel ($OEM_KERNEL_PKG)."
    apt-get install -y "$OEM_KERNEL_PKG"
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
EOF
    systemctl daemon-reload
    systemctl enable "$RESUME_UNIT"
    echo "OEM kernel installed. Rebooting; install will continue automatically."
    echo "Watch: sudo journalctl -u $RESUME_UNIT -f   (or tail -f $LOG)"
    sleep 3; reboot; exit 0
  fi
fi

# --- install phase (fresh, or auto-resumed after reboot) ---
echo "await-install" > "$STATE_FILE"
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
rm -f "$STATE_FILE"
echo ""
echo "DONE. Open the demo in a browser:  http://localhost:30890  (auto-login as 'student')"
echo "Remote: http://<this-host-ip>:30890   |  Admin: http://localhost:30890/hub/admin"
[ "$ADMIN" = "1" ] && echo "Admin UI:  http://localhost:30890/hub/admin   (you are 'student', now an admin)"
