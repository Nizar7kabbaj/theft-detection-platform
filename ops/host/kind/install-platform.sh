#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s inherit_errexit

readonly KCTX="${KCTX:-kind-theft-dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REPO_ROOT
readonly VALUES_DIR="${REPO_ROOT}/deploy/platform"
readonly EDGE_DIR="${VALUES_DIR}/edge"
readonly KEYRING="${VALUES_DIR}/keys/cert-manager-keyring.gpg"
readonly NAMESPACES="${REPO_ROOT}/deploy/cluster/namespaces.yaml"
readonly NETWORK_POLICIES="${REPO_ROOT}/deploy/cluster/network-policies.yaml"
readonly MESH_POLICIES="${REPO_ROOT}/deploy/cluster/mesh-policies.yaml"
readonly NODE_EXPORTER_ACCESS="${VALUES_DIR}/node-exporter-access.yaml"
readonly CNPG_NETWORK_POLICIES="${VALUES_DIR}/cnpg-network-policies.yaml"
readonly ISSUER_MANIFEST="${VALUES_DIR}/cluster-issuer.yaml"
readonly SERVICE_CA_DIR="${REPO_ROOT}/config/pki/ca"
readonly CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/theft-platform"
readonly EDGE_CA_DIR="${REPO_ROOT}/config/traefik/certs"
readonly MESH_CA_DIR="${REPO_ROOT}/config/pki/mesh-ca/istiod"
readonly MESH_CA_FILES=(ca-cert.pem ca-key.pem cert-chain.pem root-cert.pem)

readonly CERT_MANAGER_VERSION="v1.21.2"
readonly CERT_MANAGER_SHA256="73a56e1728edd6c99f1f31082618c3259d279a76b7ebd3d4bdc5475c2442d34a"
readonly CNPG_VERSION="0.29.1"
readonly CNPG_SHA256="b53d3991fe84bcf38767e7702cae78666265427a127a26fff168ab4207d2b1df"
readonly RELOADER_VERSION="2.2.17"
readonly RELOADER_SHA256="a17ee91d66785c29c17e5dfd038c13b0e35b23301b33f8fdb431b403d8a7a071"
readonly GATEWAY_API_VERSION="v1.6.2"
readonly GATEWAY_API_SHA256="faede450fa178126aba41337737b97d351ebe87d93c910237ce1e072d1ca40d9"
readonly ISTIO_VERSION="1.31.1"
readonly ISTIO_SHA256="cb4af2e8a099acfc51368c1d15d4deab8321ae628554d4ee5c74f62ebe775857"
readonly PROMETHEUS_REPO="https://prometheus-community.github.io/helm-charts"
readonly PROMETHEUS_VERSION="29.34.0"
readonly PROMETHEUS_SHA256="e0dc3d372c6db2f055578594eb78c96646671fec4b4e5d3613aa6f66556b4955"
readonly NODE_EXPORTER_VERSION="4.58.0"
readonly NODE_EXPORTER_SHA256="9781c208d90e95d67495fdc7985dc8d9c21a25996ae807a25b24fd191dedbeb4"

WORK_DIR=""

usage() {
  cat <<EOF
usage: $(basename "$0")

installs the platform layer into ${KCTX}: gateway api ${GATEWAY_API_VERSION}, cert-manager ${CERT_MANAGER_VERSION},
cloudnative-pg ${CNPG_VERSION}, reloader ${RELOADER_VERSION}, istio ${ISTIO_VERSION} in ambient mode with the
mesh ca from ${MESH_CA_DIR}, istio-cni and ztunnel in istio-dataplane, the public gateway,
prometheus chart ${PROMETHEUS_VERSION} and node-exporter chart ${NODE_EXPORTER_VERSION}.
every artifact is checked against a pinned sha256 and dry-run against pod security first.
EOF
}

log() { printf '%s\n' "$*" >&2; }
die() { log "error: $*"; exit 1; }
cleanup() { [[ -n "$WORK_DIR" ]] && rm -rf "$WORK_DIR"; }

require() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing command: ${cmd}"
  done
}

check_sha() {
  local file="$1" expected="$2" actual
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
  [[ "$actual" == "$expected" ]] || die "sha256 mismatch for $(basename "$file"): got ${actual}"
}

download() {
  local url="$1" sha="$2" out="${CACHE_DIR}/${1##*/}"
  mkdir -p "$CACHE_DIR"
  if [[ -f "$out" && "$(sha256sum "$out" | cut -d' ' -f1)" == "$sha" ]]; then
    log "using cached $(basename "$out")"
    printf '%s' "$out"
    return
  fi
  curl -fsSL --retry 5 --retry-all-errors --connect-timeout 15 -o "${out}.part" "$url" \
    || die "download failed: ${url}"
  check_sha "${out}.part" "$sha"
  mv "${out}.part" "$out"
  printf '%s' "$out"
}

fetch_cert_manager() {
  helm pull oci://quay.io/jetstack/charts/cert-manager \
    --version "$CERT_MANAGER_VERSION" --verify --keyring "$KEYRING" \
    --destination "$WORK_DIR" >/dev/null 2>&1 || die "cert-manager chart signature check failed"
  check_sha "${WORK_DIR}/cert-manager-${CERT_MANAGER_VERSION}.tgz" "$CERT_MANAGER_SHA256"
  printf '%s' "${WORK_DIR}/cert-manager-${CERT_MANAGER_VERSION}.tgz"
}

fetch_repo_chart() {
  local repo="$1" chart="$2" version="$3" sha="$4" out="${CACHE_DIR}/${2}-${3}.tgz"
  mkdir -p "$CACHE_DIR"
  if [[ -f "$out" && "$(sha256sum "$out" | cut -d' ' -f1)" == "$sha" ]]; then
    log "using cached $(basename "$out")"
    printf '%s' "$out"
    return
  fi
  helm pull "$chart" --repo "$repo" --version "$version" --destination "$WORK_DIR" >/dev/null \
    || die "chart download failed: ${chart} ${version}"
  check_sha "${WORK_DIR}/${chart}-${version}.tgz" "$sha"
  mv "${WORK_DIR}/${chart}-${version}.tgz" "$out"
  printf '%s' "$out"
}

fetch_istio_charts() {
  local tarball
  tarball="$(download "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istio-${ISTIO_VERSION}-linux-amd64.tar.gz" "$ISTIO_SHA256")"
  tar -xzf "$tarball" -C "$WORK_DIR" "istio-${ISTIO_VERSION}/manifests/charts"
  printf '%s' "${WORK_DIR}/istio-${ISTIO_VERSION}/manifests/charts"
}

install_gateway_api() {
  local file
  file="$(download "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" "$GATEWAY_API_SHA256")"
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$file" >/dev/null
  kubectl --context "$KCTX" wait --for=condition=Established --timeout=60s \
    crd/gateways.gateway.networking.k8s.io crd/httproutes.gateway.networking.k8s.io >/dev/null
  log "gateway api ${GATEWAY_API_VERSION} crds applied"
}

install_release() {
  local release="$1" namespace="$2" chart="$3" values="$4" out
  [[ -n "$chart" && -e "$chart" ]] || die "no chart for ${release}, the fetch before it failed"
  out="$(helm template "$release" "$chart" --namespace "$namespace" -f "$values" \
    | kubectl --context "$KCTX" apply --server-side --force-conflicts --field-manager=platform-check --dry-run=server -f - 2>&1)" \
    || die "dry run failed for ${release}: ${out}"
  if grep -qi 'would violate PodSecurity' <<<"$out"; then
    grep -i 'PodSecurity' <<<"$out" >&2
    die "${release} violates pod security restricted"
  fi
  helm upgrade --install "$release" "$chart" \
    --kube-context "$KCTX" --namespace "$namespace" -f "$values" \
    --wait --timeout 5m >/dev/null
  log "${release} installed in ${namespace}"
}

load_ca_secret() {
  local name="$1" dir="$2"
  [[ -f "${dir}/ca.crt" && -f "${dir}/ca.key" ]] || die "missing ca files in ${dir}"
  kubectl --context "$KCTX" -n cert-manager create secret tls "$name" \
    --cert "${dir}/ca.crt" --key "${dir}/ca.key" --dry-run=client -o yaml \
    | kubectl --context "$KCTX" apply --server-side --field-manager=platform -f - >/dev/null
}

load_issuers() {
  load_ca_secret theft-ca "$SERVICE_CA_DIR"
  load_ca_secret edge-ca "$EDGE_CA_DIR"
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$ISSUER_MANIFEST" >/dev/null
  kubectl --context "$KCTX" wait --for=condition=Ready --timeout=60s clusterissuer/theft-ca clusterissuer/edge-ca >/dev/null
  log "cluster issuers theft-ca and edge-ca ready"
}

load_mesh_ca() {
  local f args=()
  for f in "${MESH_CA_FILES[@]}"; do
    [[ -f "${MESH_CA_DIR}/${f}" ]] || die "missing ${f} in ${MESH_CA_DIR}, run tools/scripts/gen_mesh_ca.sh"
    args+=("--from-file=${f}=${MESH_CA_DIR}/${f}")
  done
  kubectl --context "$KCTX" -n istio-system create secret generic cacerts "${args[@]}" \
    --dry-run=client -o yaml \
    | kubectl --context "$KCTX" apply --server-side --field-manager=platform -f - >/dev/null
  log "mesh ca loaded into istio-system/cacerts"
}

apply_mesh_policies() {
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$MESH_POLICIES" >/dev/null
  log "theft mesh baseline applied: strict mtls and default deny"
}

apply_scrape_trust() {
  kubectl --context "$KCTX" -n monitoring create configmap theft-ca \
    --from-file=ca.crt="${SERVICE_CA_DIR}/ca.crt" --dry-run=client -o yaml \
    | kubectl --context "$KCTX" apply --server-side --field-manager=platform -f - >/dev/null
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$NODE_EXPORTER_ACCESS" >/dev/null
  kubectl --context "$KCTX" -n node-exporter wait --for=condition=Ready certificate/node-exporter --timeout=60s >/dev/null
  log "scrape trust ready: theft-ca in monitoring, node-exporter certificate and scrape role"
}

apply_edge() {
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$EDGE_DIR" >/dev/null
  kubectl --context "$KCTX" -n edge wait --for=condition=Ready certificate/localhost --timeout=60s >/dev/null
  kubectl --context "$KCTX" -n edge wait --for=condition=Programmed gateway/public --timeout=120s >/dev/null
  log "public gateway programmed"
}

main() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
  require helm kubectl sha256sum curl tar
  [[ -f "$KEYRING" ]] || die "missing keyring: ${KEYRING}"
  WORK_DIR="$(mktemp -d)"
  trap cleanup EXIT

  kubectl --context "$KCTX" apply --server-side --force-conflicts --field-manager=platform -f "$NAMESPACES" >/dev/null
  log "namespaces applied"
  kubectl --context "$KCTX" apply --server-side -f "$NETWORK_POLICIES" >/dev/null
  log "theft baseline network policy applied"
  install_gateway_api

  local charts
  charts="$(fetch_istio_charts)"
  install_release istio-base istio-system "${charts}/base" "${VALUES_DIR}/istio-base.yaml"
  load_mesh_ca
  install_release istiod istio-system "${charts}/istio-control/istio-discovery" "${VALUES_DIR}/istiod.yaml"
  install_release istio-cni istio-dataplane "${charts}/istio-cni" "${VALUES_DIR}/istio-cni.yaml"
  install_release ztunnel istio-dataplane "${charts}/ztunnel" "${VALUES_DIR}/ztunnel.yaml"
  apply_mesh_policies

  install_release cert-manager cert-manager "$(fetch_cert_manager)" "${VALUES_DIR}/cert-manager.yaml"
  kubectl --context "$KCTX" apply --server-side --field-manager=platform -f "$CNPG_NETWORK_POLICIES" >/dev/null
  log "cnpg-system network policies applied"
  install_release cnpg cnpg-system \
    "$(fetch_repo_chart https://cloudnative-pg.github.io/charts cloudnative-pg "$CNPG_VERSION" "$CNPG_SHA256")" \
    "${VALUES_DIR}/cloudnative-pg.yaml"
  install_release reloader reloader \
    "$(fetch_repo_chart https://stakater.github.io/stakater-charts reloader "$RELOADER_VERSION" "$RELOADER_SHA256")" \
    "${VALUES_DIR}/reloader.yaml"
  load_issuers

  install_release public-gateway edge "${charts}/gateway" "${VALUES_DIR}/gateway.yaml"
  apply_edge
  apply_scrape_trust
  install_release prometheus monitoring \
    "$(fetch_repo_chart "$PROMETHEUS_REPO" prometheus "$PROMETHEUS_VERSION" "$PROMETHEUS_SHA256")" \
    "${VALUES_DIR}/prometheus.yaml"
  install_release node-exporter node-exporter \
    "$(fetch_repo_chart "$PROMETHEUS_REPO" prometheus-node-exporter "$NODE_EXPORTER_VERSION" "$NODE_EXPORTER_SHA256")" \
    "${VALUES_DIR}/node-exporter.yaml"

  local ns
  for ns in cert-manager cnpg-system reloader istio-system istio-dataplane edge monitoring node-exporter; do
    kubectl --context "$KCTX" get pods -n "$ns"
  done
}

main "$@"
