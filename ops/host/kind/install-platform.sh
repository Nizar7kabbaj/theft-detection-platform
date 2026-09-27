#!/usr/bin/env bash
set -Eeuo pipefail

readonly KCTX="${KCTX:-kind-theft-dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REPO_ROOT
readonly VALUES_DIR="${REPO_ROOT}/deploy/platform"
readonly EDGE_DIR="${VALUES_DIR}/edge"
readonly KEYRING="${VALUES_DIR}/keys/cert-manager-keyring.gpg"
readonly NAMESPACES="${REPO_ROOT}/deploy/cluster/namespaces.yaml"
readonly ISSUER_MANIFEST="${VALUES_DIR}/cluster-issuer.yaml"
readonly SERVICE_CA_DIR="${REPO_ROOT}/config/pki/ca"
readonly EDGE_CA_DIR="${REPO_ROOT}/config/traefik/certs"

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
cloudnative-pg ${CNPG_VERSION}, reloader ${RELOADER_VERSION}, istio ${ISTIO_VERSION}, the public gateway,
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
  local url="$1" sha="$2" out="${WORK_DIR}/${1##*/}"
  curl -fsSL -o "$out" "$url" || die "download failed: ${url}"
  check_sha "$out" "$sha"
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
  local repo="$1" chart="$2" version="$3" sha="$4"
  helm pull "$chart" --repo "$repo" --version "$version" --destination "$WORK_DIR" >/dev/null
  check_sha "${WORK_DIR}/${chart}-${version}.tgz" "$sha"
  printf '%s' "${WORK_DIR}/${chart}-${version}.tgz"
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

  kubectl --context "$KCTX" apply -f "$NAMESPACES" >/dev/null
  log "namespaces applied"
  install_gateway_api

  install_release cert-manager cert-manager "$(fetch_cert_manager)" "${VALUES_DIR}/cert-manager.yaml"
  install_release cnpg cnpg-system \
    "$(fetch_repo_chart https://cloudnative-pg.github.io/charts cloudnative-pg "$CNPG_VERSION" "$CNPG_SHA256")" \
    "${VALUES_DIR}/cloudnative-pg.yaml"
  install_release reloader reloader \
    "$(fetch_repo_chart https://stakater.github.io/stakater-charts reloader "$RELOADER_VERSION" "$RELOADER_SHA256")" \
    "${VALUES_DIR}/reloader.yaml"
  load_issuers

  local charts
  charts="$(fetch_istio_charts)"
  install_release istio-base istio-system "${charts}/base" "${VALUES_DIR}/istio-base.yaml"
  install_release istiod istio-system "${charts}/istio-control/istio-discovery" "${VALUES_DIR}/istiod.yaml"
  install_release public-gateway edge "${charts}/gateway" "${VALUES_DIR}/gateway.yaml"
  apply_edge
  install_release prometheus monitoring \
    "$(fetch_repo_chart "$PROMETHEUS_REPO" prometheus "$PROMETHEUS_VERSION" "$PROMETHEUS_SHA256")" \
    "${VALUES_DIR}/prometheus.yaml"
  install_release node-exporter node-exporter \
    "$(fetch_repo_chart "$PROMETHEUS_REPO" prometheus-node-exporter "$NODE_EXPORTER_VERSION" "$NODE_EXPORTER_SHA256")" \
    "${VALUES_DIR}/node-exporter.yaml"

  local ns
  for ns in cert-manager cnpg-system reloader istio-system edge monitoring node-exporter; do
    kubectl --context "$KCTX" get pods -n "$ns"
  done
}

main "$@"
