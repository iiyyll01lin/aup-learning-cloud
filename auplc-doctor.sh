#!/usr/bin/env bash
# auplc-doctor.sh - diagnose & fix why AUP Learning Cloud doesn't auto-start after reboot.
#   sudo ./auplc-doctor.sh          # diagnose + auto-fix + verify
#   sudo ./auplc-doctor.sh --check  # diagnose only (no changes)
set -uo pipefail   # intentionally NOT -e: run all checks even if some fail

NODE_IP="10.255.255.1"
KCFG="/etc/rancher/k3s/k3s.yaml"
DROPIN="/etc/systemd/system/k3s.service.d/10-auplc-autostart.conf"
DUMMY_UNIT="/etc/systemd/system/dummy-interface.service"
MODE="fix"; [ "${1:-}" = "--check" ] && MODE="check"
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
export KUBECONFIG="$KCFG"
ok(){ echo "  [OK]   $*"; }; warn(){ echo "  [WARN] $*"; }; bad(){ echo "  [FAIL] $*"; }; act(){ echo "  [FIX]  $*"; }

echo "== AUPLC autostart doctor ($(date)) mode=$MODE =="
if ! command -v k3s >/dev/null 2>&1 && [ ! -x /usr/local/bin/k3s ]; then
  bad "k3s not installed - this is not an autostart problem. Run: sudo ./demo-setup.sh"; exit 1
fi
DOCKER_MODE=0
grep -rqs -- '--docker' /etc/systemd/system/k3s.service* 2>/dev/null && DOCKER_MODE=1

echo "--- Diagnosis ---"
echo "  kernel=$(uname -r) runtime=$([ $DOCKER_MODE = 1 ] && echo docker || echo containerd)"
ip -o addr show dummy0 2>/dev/null | grep -q "$NODE_IP" && ok "dummy0 has $NODE_IP" || bad "dummy0 missing/no IP $NODE_IP"
for svc in dummy-interface.service docker.service k3s.service; do
  { [ "$svc" = docker.service ] && [ "$DOCKER_MODE" != 1 ]; } && continue
  echo "  $svc: enabled=$(systemctl is-enabled "$svc" 2>/dev/null || echo missing) active=$(systemctl is-active "$svc" 2>/dev/null || echo inactive)"
done
[ "$DOCKER_MODE" = 1 ] && { [ -f "$DROPIN" ] && ok "k3s docker-ordering drop-in present" || warn "no k3s docker-ordering drop-in"; }
echo "  recent k3s log:"; journalctl -u k3s -b --no-pager 2>/dev/null | tail -n 15 | sed 's/^/    /'
kubectl get nodes 2>&1 | sed 's/^/  nodes: /'
[ "$MODE" = check ] && { echo "--- check mode: no changes ---"; exit 0; }

echo "--- Applying fixes ---"
echo dummy > /etc/modules-load.d/auplc-dummy.conf; modprobe dummy 2>/dev/null || true
cat > "$DUMMY_UNIT" <<EOF
[Unit]
Description=Setup dummy network interface for K3s portable operation
Before=k3s.service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/sbin/modprobe dummy
ExecStart=/bin/bash -c 'ip link show dummy0 >/dev/null 2>&1 || ip link add dummy0 type dummy; ip link set dummy0 up; ip addr replace ${NODE_IP}/32 dev dummy0'
ExecStop=/bin/bash -c 'ip link del dummy0 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
EOF
act "rewrote $DUMMY_UNIT (idempotent IP via 'ip addr replace' + modprobe dummy)"
if [ "$DOCKER_MODE" = 1 ]; then
  systemctl enable docker 2>/dev/null || true
  mkdir -p "$(dirname "$DROPIN")"
  printf '[Unit]\nAfter=docker.service dummy-interface.service\nWants=docker.service dummy-interface.service\n' > "$DROPIN"
  act "wrote $DROPIN (k3s waits for docker + dummy0)"
fi
systemctl daemon-reload
systemctl enable dummy-interface.service k3s 2>/dev/null || true
systemctl restart dummy-interface.service || true
systemctl restart k3s || true
act "enabled + restarted dummy-interface and k3s"

echo "--- Verifying ---"
for _ in $(seq 1 30); do kubectl get nodes 2>/dev/null | grep -q ' Ready' && break; sleep 5; done
kubectl get nodes 2>&1 | sed 's/^/  /'; kubectl get pods -n jupyterhub 2>&1 | sed 's/^/  /'
curl -sf http://localhost:30890/hub/health >/dev/null 2>&1 && ok "reachable: http://localhost:30890" || warn "not reachable yet; pods may still be starting"
echo ""
echo "DONE. Then 'sudo reboot' once and re-run 'sudo ./auplc-doctor.sh --check' to confirm it survives a real power cycle."
