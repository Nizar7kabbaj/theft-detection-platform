#!/usr/bin/env bash
set -Eeuo pipefail

readonly KCTX="${KCTX:-kind-theft-dev}"
readonly NAMESPACE="theft"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REPO_ROOT
readonly CHART="${REPO_ROOT}/deploy/helm/theft-detection-platform"
readonly IMAGE_VALUES="${REPO_ROOT}/.build/image-values.yaml"

usage() {
  cat <<EOF
usage: $(basename "$0") <command> [options]

runs one audit operator command as a job in ${NAMESPACE}, streams its log and exits with its status.

  seal [--dry-run] [--max-segments N]
  erase --subject ID --requested-by NAME [--dry-run]
  verify
  status
EOF
}

log() { printf '%s\n' "$*" >&2; }
die() { log "error: $*"; exit 1; }

require() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing command: ${cmd}"
  done
}

k() { kubectl --context "$KCTX" -n "$NAMESPACE" "$@"; }

wait_started() {
  local name="$1" phase="" i
  for ((i = 0; i < 120; i++)); do
    phase="$(k get pods -l "batch.kubernetes.io/job-name=${name}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)"
    [[ "$phase" == "Running" || "$phase" == "Succeeded" || "$phase" == "Failed" ]] && return 0
    sleep 1
  done
  die "job ${name} did not start within 120s"
}

main() {
  case "${1:-}" in
    -h | --help) usage; exit 0 ;;
    seal | erase | verify | status) ;;
    *) usage; exit 2 ;;
  esac
  require helm kubectl jq
  [[ -s "$IMAGE_VALUES" ]] || die "missing ${IMAGE_VALUES#"${REPO_ROOT}/"}, run tools/scripts/build_images.sh first"

  local name args
  name="audit-operator-$1-$(date -u +%Y%m%d%H%M%S)"
  args="$(printf '%s\n' "$@" | jq -R . | jq -cs .)"

  helm template theft-app "$CHART" --namespace "$NAMESPACE" \
    -f "${CHART}/values-dev.yaml" -f "$IMAGE_VALUES" \
    --set auditOperator.run=true \
    --set-string auditOperator.name="$name" \
    --set-json "auditOperator.args=${args}" \
    --show-only templates/audit-operator.yaml \
    | kubectl --context "$KCTX" apply --server-side --field-manager=audit-operator -f - >/dev/null
  log "job ${name} created"

  wait_started "$name"
  k logs -f "job/${name}"

  local state="" i
  for ((i = 0; i < 60; i++)); do
    state="$(k get job "$name" -o jsonpath='{.status.conditions[?(@.status=="True")].type}')"
    [[ "$state" == *Complete* || "$state" == *Failed* ]] && break
    sleep 1
  done
  if [[ "$state" == *Complete* ]]; then
    log "job ${name} succeeded"
    return 0
  fi
  log "job ${name} failed, kept for ${NAMESPACE} inspection until ttl"
  return 1
}

main "$@"
