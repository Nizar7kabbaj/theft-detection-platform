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
readonly REGISTRY_CONFIG="${REPO_ROOT}/ops/host/kind/registry-config.yml"
readonly NETWORK_NAME="kind"
readonly NETWORK_SUBNET="172.19.0.0/16"
readonly NETWORK_GATEWAY="172.19.0.1"
readonly NETWORK_SUBNET6="fc00:f853:ccd:e793::/64"
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

ensure_network() {
  if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    log "network ${NETWORK_NAME} present"
    return
  fi
  docker network create "$NETWORK_NAME" \
    --driver bridge \
    --subnet "$NETWORK_SUBNET" --gateway "$NETWORK_GATEWAY" \
    --ipv6 --subnet "$NETWORK_SUBNET6" \
    --opt com.docker.network.bridge.enable_ip_masquerade=true \
    --opt com.docker.network.driver.mtu=1500 >/dev/null
  log "network ${NETWORK_NAME} created before the registry so node addresses stay in order"
}

registry_spec() {
  printf '%s\n' "$REGISTRY_IMAGE" "$REGISTRY_IP" "restart=no" "log=10m*3" \
    "$(sha256sum "$REGISTRY_CONFIG" | cut -d' ' -f1)" | sha256sum | cut -c1-16
}

ensure_registry() {
  local spec
  [[ -f "$REGISTRY_CONFIG" ]] || die "missing ${REGISTRY_CONFIG}"
  spec="$(registry_spec)"
  if docker container inspect "$REGISTRY_NAME" >/dev/null 2>&1 \
    && [[ "$(docker inspect -f '{{index .Config.Labels "theft.registry.spec"}}' "$REGISTRY_NAME")" != "$spec" ]]; then
    docker rm -f "$REGISTRY_NAME" >/dev/null
    log "registry settings changed, container replaced, data volume kept"
  fi
  if ! docker container inspect "$REGISTRY_NAME" >/dev/null 2>&1; then
    docker run -d \
      --name "$REGISTRY_NAME" \
      --label "theft.registry.spec=${spec}" \
      --restart no \
      --network "$NETWORK_NAME" --ip "$REGISTRY_IP" \
      --read-only \
      --tmpfs /tmp \
      --cap-drop ALL \
      --security-opt no-new-privileges:true \
      --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
      -p "127.0.0.1:${REGISTRY_PORT}:5000" \
      -v kind-registry-data:/var/lib/registry \
      --mount "type=bind,source=${REGISTRY_CONFIG},target=/etc/distribution/config.yml,readonly" \
      "$REGISTRY_IMAGE" >/dev/null
    log "registry started at ${REGISTRY_IP}"
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
  kubectl --context "$KCTX" apply --server-side --force-conflicts --field-manager=platform -f "$NAMESPACE_MANIFEST" >/dev/null
  log "namespace theft applied"
  kubectl --context "$KCTX" apply --server-side -f "$NETWORK_POLICY_MANIFEST" >/dev/null
  log "theft baseline network policy applied"
}

readonly REGISTRY_IP=172.19.0.2
readonly NODE_IPS="172.19.0.3 172.19.0.4"

node_ip() {
  docker inspect -f '{{with index .NetworkSettings.Networks "kind"}}{{.IPAddress}}{{end}}' "$1"
}

node_pin() {
  docker inspect -f '{{with index .NetworkSettings.Networks "kind"}}{{with .IPAMConfig}}{{.IPv4Address}}{{end}}{{end}}' "$1"
}

pin_addresses() {
  local name nodes pinned=1
  [[ "$(node_ip "$REGISTRY_NAME")" == "$REGISTRY_IP" ]] \
    || die "${REGISTRY_NAME} came up at $(node_ip "$REGISTRY_NAME"), expected ${REGISTRY_IP}"
  nodes="$(printf '%s\n' "$(node_ip "${CLUSTER_NAME}-control-plane")" "$(node_ip "${CLUSTER_NAME}-worker")" | sort | paste -sd' ')"
  [[ "$nodes" == "$NODE_IPS" ]] || die "nodes came up at ${nodes}, the address plan expects ${NODE_IPS}"
  for name in "$REGISTRY_NAME" "${CLUSTER_NAME}-control-plane" "${CLUSTER_NAME}-worker"; do
    [[ "$(node_pin "$name")" == "$(node_ip "$name")" ]] || pinned=0
  done
  if (( pinned )); then
    log "node addresses already pinned"
    return
  fi
  "$(dirname "${BASH_SOURCE[0]}")/cluster.sh" stop
  "$(dirname "${BASH_SOURCE[0]}")/cluster.sh" start
  log "node addresses pinned and auto restart disabled"
}

csr_sans() {
  base64 -d | openssl req -noout -text \
    | awk '/Subject Alternative Name/ { getline; gsub(/ /, ""); print }'
}

approve_kubelet_serving() {
  local node ip expected listing name user cond sans
  for node in "${CLUSTER_NAME}-control-plane" "${CLUSTER_NAME}-worker"; do
    ip="$(kubectl --context "$KCTX" get node "$node" \
      -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
    [[ -n "$ip" ]] || die "node ${node} has no internal ip"
    expected="DNS:${node},IPAddress:${ip}"
    for _ in $(seq 1 60); do
      listing="$(kubectl --context "$KCTX" get csr \
        --field-selector spec.signerName=kubernetes.io/kubelet-serving \
        -o jsonpath='{range .items[*]}{.metadata.name} {.spec.username} {.status.conditions[*].type}{"\n"}{end}')"
      while read -r name user cond; do
        [[ -n "$name" && "$user" == "system:node:${node}" && -z "$cond" ]] || continue
        sans="$(kubectl --context "$KCTX" get csr "$name" -o jsonpath='{.spec.request}' | csr_sans)"
        [[ "$sans" == "$expected" ]] \
          || die "serving request ${name} for ${node} asks for ${sans}, expected ${expected}"
        kubectl --context "$KCTX" certificate approve "$name" >/dev/null
      done <<<"$listing"
      kubectl --context "$KCTX" get --raw "/api/v1/nodes/${node}/proxy/healthz" >/dev/null 2>&1 && break
      sleep 2
    done
    kubectl --context "$KCTX" get --raw "/api/v1/nodes/${node}/proxy/healthz" >/dev/null 2>&1 \
      || die "kubelet on ${node} has no serving certificate"
    log "kubelet serving certificate issued for ${node} (${ip})"
  done
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
  require docker kind kubectl sudo openssl base64
  ensure_encryption_config
  ensure_snapshot_dir
  ensure_network
  ensure_registry
  create_cluster
  connect_registry
  apply_namespace
  approve_kubelet_serving
  verify_encryption
  pin_addresses
  log "cluster ${CLUSTER_NAME} ready"
}

main "$@"
