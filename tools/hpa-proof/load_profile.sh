#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?usage: load_profile.sh single|scaled|off}"
C="${repo}/deploy/helm/theft-detection-platform"
edge="${repo}/deploy/platform/edge/rate-limit.yaml"
raised="${repo}/.build/edge-rate-limit-load.yaml"

base=(upgrade --install theft-app "$C" -n theft -f "$C/values-dev.yaml" -f "${repo}/.build/image-values.yaml" --wait --timeout 10m)
load=(
  --set-string components.backend.env.RATE_LIMIT_REQUESTS=1000000
  --set-string components.backend.env.RATE_LIMIT_BURST=1000000
)

apply_edge() {
  kubectl apply --server-side --force-conflicts --field-manager=platform -f "$1" >/dev/null
}

case "$mode" in
  single)
    uv run --no-project --with pyyaml python "${repo}/tools/hpa-proof/edge_profile.py" "$edge" "$raised"
    apply_edge "$raised"
    helm "${base[@]}" "${load[@]}" --set components.backend.autoscaling.maxReplicas=1
    ;;
  scaled)
    uv run --no-project --with pyyaml python "${repo}/tools/hpa-proof/edge_profile.py" "$edge" "$raised"
    apply_edge "$raised"
    helm "${base[@]}" "${load[@]}"
    ;;
  off)
    apply_edge "$edge"
    helm "${base[@]}"
    ;;
  *)
    echo "unknown mode ${mode}" >&2
    exit 2
    ;;
esac
echo "load profile ${mode} applied"
