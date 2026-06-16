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
GPU_DS="amdgpu-device-plugin-daemonset amdgpu-labeller-daemonset"
GPU_IMAGES="rocm/k8s-device-plugin:latest rocm/k8s-device-plugin:labeller-latest"
GPU_PULL_POLICY_PATCH='[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"}]'

containerd_crictl_available(){
  command -v k3s >/dev/null 2>&1 || [ -x /usr/local/bin/k3s ] || command -v crictl >/dev/null 2>&1
}
crictl_images(){
  if command -v k3s >/dev/null 2>&1; then k3s crictl images 2>/dev/null
  elif [ -x /usr/local/bin/k3s ]; then /usr/local/bin/k3s crictl images 2>/dev/null
  elif command -v crictl >/dev/null 2>&1; then crictl images 2>/dev/null
  else return 127
  fi
}
image_cached(){
  img="$1"
  if [ "$DOCKER_MODE" = 1 ]; then
    docker image inspect "$img" >/dev/null 2>&1
  else
    repo="${img%:*}"; tag="${img##*:}"
    crictl_images | awk -v repo="$repo" -v tag="$tag" '
      function endswith(s, suffix) { return length(s) >= length(suffix) && substr(s, length(s) - length(suffix) + 1) == suffix }
      NR > 1 {
        if (($1 == repo || endswith($1, "/" repo)) && $2 == tag) found=1
        if ($1 == repo ":" tag || endswith($1, "/" repo ":" tag)) found=1
      }
      END { exit found ? 0 : 1 }
    '
  fi
}
report_gpu_image_cache(){
  if [ "$DOCKER_MODE" != 1 ] && ! containerd_crictl_available; then
    warn "cannot inspect containerd image cache (no k3s crictl/crictl)"
    return
  fi
  for img in $GPU_IMAGES; do
    image_cached "$img" && ok "cached image: $img" || warn "missing cached image: $img"
  done
}
patch_gpu_daemonset(){
  ds="$1"
  if kubectl -n kube-system get ds "$ds" >/dev/null 2>&1; then
    kubectl -n kube-system patch ds "$ds" --type=json -p "$GPU_PULL_POLICY_PATCH" >/dev/null 2>&1 \
      && act "patched $ds imagePullPolicy=IfNotPresent" \
      || warn "failed to patch $ds imagePullPolicy"
  else
    warn "$ds not found; skipping GPU policy patch"
  fi
}
ensure_gpu_image(){
  img="$1"
  image_cached "$img" && return
  if [ "$DOCKER_MODE" = 1 ]; then
    act "pulling missing image $img"
    docker pull "$img" >/dev/null 2>&1 \
      && ok "seeded image cache: $img" \
      || warn "missing $img and docker pull failed; connect once to seed this image"
  else
    warn "missing $img in containerd image cache; connect once or pre-seed this image"
  fi
}
verify_gpu_daemonset_ready(){
  ds="$1"
  kubectl -n kube-system get ds "$ds" >/dev/null 2>&1 || return
  for _ in $(seq 1 12); do
    ready=$(kubectl -n kube-system get ds "$ds" -o jsonpath='{.status.numberReady}' 2>/dev/null || true)
    desired=$(kubectl -n kube-system get ds "$ds" -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || true)
    [ -z "$ready" ] && ready=0
    if [ "$ready" -ge 1 ] 2>/dev/null; then
      ok "$ds ready ($ready/${desired:-?})"
      return
    fi
    sleep 5
  done
  warn "$ds not ready yet"
}

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
systemctl show k3s.service -p After --value 2>/dev/null | grep -q network-online.target && warn "k3s still ordered After network-online.target (will hang on offline boot)" || ok "k3s not waiting on network-online"
for wsvc in NetworkManager-wait-online.service systemd-networkd-wait-online.service; do echo "  $wsvc: enabled=$(systemctl is-enabled "$wsvc" 2>/dev/null || echo missing)"; done
for ds in $GPU_DS; do
  pol=$(kubectl -n kube-system get ds "$ds" -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}' 2>/dev/null || true)
  if [ -z "$pol" ]; then
    warn "$ds not found"
  elif [ "$pol" = Always ]; then
    warn "$ds imagePullPolicy=Always (offline reboot can ImagePullBackOff)"
  else
    ok "$ds imagePullPolicy=$pol"
  fi
done
echo "  amdgpu pods:"
kubectl -n kube-system get pods 2>/dev/null | grep -E 'amdgpu-(device-plugin|labeller)' | sed 's/^/    /' || echo "    (none found)"
report_gpu_image_cache
echo "  recent k3s log:"; journalctl -u k3s -b --no-pager 2>/dev/null | tail -n 15 | sed 's/^/    /'
kubectl get nodes 2>&1 | sed 's/^/  nodes: /'
[ "$MODE" = check ] && { echo "--- check mode: no changes ---"; exit 0; }

echo "--- Applying fixes ---"
echo dummy > /etc/modules-load.d/auplc-dummy.conf; modprobe dummy 2>/dev/null || true
cat > "$DUMMY_UNIT" <<EOF
[Unit]
Description=Setup dummy network interface for K3s portable operation
Before=k3s.service
After=network-pre.target

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
mkdir -p "$(dirname "$DROPIN")"
if [ "$DOCKER_MODE" = 1 ]; then
  systemctl enable docker 2>/dev/null || true
  printf '[Unit]\nWants=\nAfter=\nAfter=docker.service dummy-interface.service\nWants=docker.service dummy-interface.service\n' > "$DROPIN"
  act "wrote $DROPIN (reset network-online wait; k3s waits for docker + dummy0)"
else
  printf '[Unit]\nWants=\nAfter=\nAfter=dummy-interface.service\nWants=dummy-interface.service\n' > "$DROPIN"
  act "wrote $DROPIN (reset network-online wait; k3s waits for dummy0)"
fi
systemctl daemon-reload
systemctl enable dummy-interface.service k3s 2>/dev/null || true
systemctl restart dummy-interface.service || true
systemctl restart k3s || true
act "enabled + restarted dummy-interface and k3s"
for img in $GPU_IMAGES; do ensure_gpu_image "$img"; done
for ds in $GPU_DS; do patch_gpu_daemonset "$ds"; done
kubectl -n kube-system rollout restart ds/amdgpu-device-plugin-daemonset ds/amdgpu-labeller-daemonset >/dev/null 2>&1 \
  && act "restarted ROCm GPU DaemonSets" \
  || warn "ROCm GPU DaemonSet restart skipped or incomplete"

echo "--- Verifying ---"
for _ in $(seq 1 30); do kubectl get nodes 2>/dev/null | grep -q ' Ready' && break; sleep 5; done
kubectl get nodes 2>&1 | sed 's/^/  /'; kubectl get pods -n jupyterhub 2>&1 | sed 's/^/  /'
for ds in $GPU_DS; do
  verify_gpu_daemonset_ready "$ds"
done
gpu_alloc=$(kubectl get nodes -o jsonpath='{.items[0].status.allocatable.amd\.com/gpu}' 2>/dev/null || true)
[ -n "$gpu_alloc" ] && ok "amd.com/gpu allocatable=$gpu_alloc" || warn "amd.com/gpu allocatable not reported yet"
curl -sf http://localhost:30890/hub/health >/dev/null 2>&1 && ok "reachable: http://localhost:30890" || warn "not reachable yet; pods may still be starting"
echo ""
echo "DONE. Then 'sudo reboot' once and re-run 'sudo ./auplc-doctor.sh --check' to confirm it survives a real power cycle."
