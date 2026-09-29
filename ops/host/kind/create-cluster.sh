#!/usr/bin/env bash
set -Eeuo pipefail

readonly CLUSTER_NAME="theft-dev"
readonly KCTX="kind-${CLUSTER_NAME}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REPO_ROOT
readonly CLUSTER_CONFIG="${REPO_ROOT}/infra/kind/cluster.yaml"
readonly NAMESPACE_MANIFEST="${REPO_ROOT}/deploy/cluster/namespaces.yaml"
readonly NETWORK_POLICY_MANIFEST="${REPO_ROOT}/deploy/cluster/network-policies.yaml"
readonly ENCRYPTION_DIR="/etc/theft-kind"
readonly ENCRYPTION_FILE="${ENCRYPTION_DIR}/encryption.yaml"
readonly SNAPSHOT_DIR="/srv/theft/snapshots"
readonly REGISTRY_NAME="kind-registry"
readonly REGISTRY_PORT="5001"
readonly REGISTRY_IMAGE="registry@sha256:852b3e4d378c426dda6b318fe9d9bfe8e92a0eccb9926671ec3d3ea17a196696"
readonly READY_TIMEOUT_SECONDS=180

usage() {
  cat <<EOF
usage: $(basename "$0")

creates the ${CLUSTER_NAME} kind cluster with a local registry on 127.0.0.1:${REGISTRY_PORT},
secrets encrypted at rest and the theft namespace. safe to run again.
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

ensure_encryption_config() {
  if sudo test -s "$ENCRYPTION_FILE"; then
    log "encryption config present"
    return
  fi
  sudo install -d -o root -g root -m 0700 "$ENCRYPTION_DIR"
  sudo sh -c 'umask 077 && key="$(head -c 32 /dev/urandom | base64)" && printf "%s\n" \
    "apiVersion: apiserver.config.k8s.io/v1" \
    "kind: EncryptionConfiguration" \
    "resources:" \
    "  - resources:" \
    "      - secrets" \
    "    providers:" \
    "      - secretbox:" \
    "          keys:" \
    "            - name: key1" \
    "              secret: ${key}" \
    "      - identity: {}" > "$1"' sh "$ENCRYPTION_FILE"
  log "encryption config written"
}

ensure_snapshot_dir() {
  sudo install -d -o 1000 -g 1000 -m 0750 "$SNAPSHOT_DIR"
  log "snapshot dir ready"
}

ensure_registry() {
  if ! docker container inspect "$REGISTRY_NAME" >/dev/null 2>&1; then
    docker run -d \
      --name "$REGISTRY_NAME" \
      --restart unless-stopped \
      --read-only \
      --tmpfs /tmp \
      --cap-drop ALL \
      --security-opt no-new-privileges:true \
      -p "127.0.0.1:${REGISTRY_PORT}:5000" \
      -v kind-registry-data:/var/lib/registry \
      "$REGISTRY_IMAGE" >/dev/null
    log "registry started"
  elif [[ "$(docker inspect -f '{{.State.Running}}' "$REGISTRY_NAME")" != "true" ]]; then
    docker start "$REGISTRY_NAME" >/dev/null
    log "registry restarted"
  else
    log "registry running"
  fi
}

create_cluster() {
  if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
    log "cluster ${CLUSTER_NAME} exists"
  else
    kind create cluster --config "$CLUSTER_CONFIG"
  fi
  local waited=0
  until kubectl --context "$KCTX" get --raw='/readyz' >/dev/null 2>&1; do
    (( waited >= READY_TIMEOUT_SECONDS )) && die "api server not ready after ${READY_TIMEOUT_SECONDS}s"
    sleep 2
    waited=$(( waited + 2 ))
  done
  log "api server ready"
}

connect_registry() {
  if [[ "$(docker inspect -f '{{json .NetworkSettings.Networks.kind}}' "$REGISTRY_NAME")" == "null" ]]; then
    docker network connect kind "$REGISTRY_NAME"
  fi
  local node dir="/etc/containerd/certs.d/localhost:${REGISTRY_PORT}"
  for node in $(kind get nodes --name "$CLUSTER_NAME"); do
    docker exec "$node" mkdir -p "$dir"
    printf '[host."http://%s:5000"]\n' "$REGISTRY_NAME" | docker exec -i "$node" cp /dev/stdin "${dir}/hosts.toml"
  done
  kubectl --context "$KCTX" apply -f - >/dev/null <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${REGISTRY_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF
  log "registry wired into nodes"
}

apply_namespace() {
  kubectl --context "$KCTX" apply -f "$NAMESPACE_MANIFEST" >/dev/null
  log "namespace theft applied"
  kubectl --context "$KCTX" apply --server-side -f "$NETWORK_POLICY_MANIFEST" >/dev/null
  log "theft baseline network policy applied"
}

verify_encryption() {
  local probe="encryption-probe" prefix
  kubectl --context "$KCTX" -n theft create secret generic "$probe" \
    --from-literal=probe=check --dry-run=client -o yaml \
    | kubectl --context "$KCTX" apply -f - >/dev/null
  prefix="$(kubectl --context "$KCTX" -n kube-system exec "etcd-${CLUSTER_NAME}-control-plane" -- \
    etcdctl --endpoints=https://127.0.0.1:2379 \
      --cacert=/etc/kubernetes/pki/etcd/ca.crt \
      --cert=/etc/kubernetes/pki/etcd/server.crt \
      --key=/etc/kubernetes/pki/etcd/server.key \
      get "/registry/secrets/theft/${probe}" --print-value-only | head -c 26)"
  kubectl --context "$KCTX" -n theft delete secret "$probe" >/dev/null
  [[ "$prefix" == "k8s:enc:secretbox:v1:key1:" ]] || die "secrets are not encrypted at rest"
  log "secrets encrypted at rest with secretbox"
}

main() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
  require docker kind kubectl sudo
  ensure_encryption_config
  ensure_snapshot_dir
  ensure_registry
  create_cluster
  connect_registry
  apply_namespace
  verify_encryption
  log "cluster ${CLUSTER_NAME} ready"
}

main "$@"
