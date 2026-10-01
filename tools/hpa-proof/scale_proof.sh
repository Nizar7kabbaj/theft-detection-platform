#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

restore() {
  kubectl -n theft patch hpa backend --type merge -p '{"spec":{"minReplicas":1}}' >/dev/null || true
}
trap restore EXIT

ready_pods() {
  kubectl -n theft get deploy backend -o jsonpath='{.status.readyReplicas}'
}

kubectl -n theft patch hpa backend --type merge -p '{"spec":{"minReplicas":3}}' >/dev/null
for _ in $(seq 1 60); do
  [[ "$(ready_pods)" == "3" ]] && break
  sleep 5
done
[[ "$(ready_pods)" == "3" ]] || { echo "backend did not reach 3 ready pods" >&2; exit 1; }
echo "backend at 3 ready pods"

since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
rc=0
uv run --no-project --with httpx==0.28.1 --with websockets==15.0.1 \
  python "${repo}/tools/hpa-proof/scale_proof.py" || rc=$?

echo "per pod during the proof"
for pod in $(kubectl -n theft get pods -l app.kubernetes.io/name=backend -o name); do
  logs="$(kubectl -n theft logs "$pod" --since-time="$since")"
  printf '  %s alert_sockets=%s camera_sockets=%s repeat_alerts=%s\n' "${pod#pod/}" \
    "$(grep -c 'websocket registered topic=alerts' <<<"$logs" || true)" \
    "$(grep -c 'websocket registered topic=cameras' <<<"$logs" || true)" \
    "$(grep -c 'already recorded' <<<"$logs" || true)"
done

for _ in 1 2 3; do
  kubectl -n theft exec -i deploy/backend -- python - <"${repo}/tools/hpa-proof/policy_state.py"
  sleep 10
done
exit "$rc"
