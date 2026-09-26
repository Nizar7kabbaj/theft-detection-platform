#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(curl gpg awk sha256sum sysctl apt-get apt-mark dpkg install)
SCRIPT_NAME=$(basename "$0")
KIND_VERSION=v0.33.0
KIND_SHA256=aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d
KIND_URL="https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
KIND_BIN=/usr/local/bin/kind
KUBE_MINOR=v1.37
KUBE_REPO="https://pkgs.k8s.io/core:/stable:/${KUBE_MINOR}/deb/"
KUBE_REPO_FINGERPRINT=DE15B14486CD377B9E876E1A234654DA9A296436
KEYRING_DIR=/etc/apt/keyrings
KEYRING="${KEYRING_DIR}/kubernetes-apt-keyring.gpg"
SOURCE_FILE=/etc/apt/sources.list.d/kubernetes.sources
SYSCTL_FILE=/etc/sysctl.d/99-kind.conf
INOTIFY_INSTANCES=512
INOTIFY_WATCHES=524288
TMP_DIR=""

function usage() {
    cat <<EOM
install kubectl and kind for the local kubernetes cluster.

usage: sudo ${SCRIPT_NAME} [options]

options:
    -h|--help    show this help

runs idempotently. pins the kind binary hash and the kubernetes apt key fingerprint.
EOM
    exit 1
}

function main() {
    if [[ $# -gt 0 ]]; then
        case $1 in
            -h|--help) usage ;;
            *) echo "unknown option: $1" >&2; usage ;;
        esac
    fi
    if [[ ${EUID} -ne 0 ]]; then
        echo "must run as root, use sudo" >&2
        exit 1
    fi
    check_deps
    check_arch
    TMP_DIR=$(mktemp -d)
    trap cleanup EXIT
    set_inotify
    install_kubectl
    install_kind
    verify
}

function cleanup() {
    if [[ -n "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi
}

function check_deps() {
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            echo "missing dependency: ${dep}" >&2
            exit 1
        fi
    done
}

function check_arch() {
    local arch
    arch=$(dpkg --print-architecture)
    if [[ "${arch}" != "amd64" ]]; then
        echo "unsupported architecture: ${arch}" >&2
        exit 1
    fi
}

function set_inotify() {
    printf 'fs.inotify.max_user_instances = %s\nfs.inotify.max_user_watches = %s\n' \
        "${INOTIFY_INSTANCES}" "${INOTIFY_WATCHES}" > "${SYSCTL_FILE}"
    chmod 644 "${SYSCTL_FILE}"
    sysctl --load="${SYSCTL_FILE}" >/dev/null
}

function install_kubectl() {
    local key="${TMP_DIR}/kubernetes.key" gnupg_home="${TMP_DIR}/gnupg" fingerprint
    install -d -m 700 "${gnupg_home}"
    curl -fsSL "${KUBE_REPO}Release.key" -o "${key}"
    fingerprint=$(GNUPGHOME="${gnupg_home}" gpg --batch --show-keys --with-colons "${key}" \
        | awk -F: '$1 == "fpr" && !seen { print $10; seen = 1 }')
    if [[ "${fingerprint}" != "${KUBE_REPO_FINGERPRINT}" ]]; then
        echo "kubernetes apt key fingerprint mismatch: ${fingerprint:-none}" >&2
        exit 1
    fi
    install -d -m 755 "${KEYRING_DIR}"
    GNUPGHOME="${gnupg_home}" gpg --batch --yes --dearmor --output "${KEYRING}" "${key}"
    chmod 644 "${KEYRING}"
    cat > "${SOURCE_FILE}" <<EOS
Types: deb
URIs: ${KUBE_REPO}
Suites: /
Signed-By: ${KEYRING}
EOS
    chmod 644 "${SOURCE_FILE}"
    apt-get update -qq
    apt-mark unhold kubectl >/dev/null 2>&1 || true
    apt-get install -y -qq kubectl >/dev/null
    apt-mark hold kubectl >/dev/null
}

function install_kind() {
    local file="${TMP_DIR}/kind"
    curl -fsSL "${KIND_URL}" -o "${file}"
    if ! echo "${KIND_SHA256}  ${file}" | sha256sum --check --status; then
        echo "kind checksum mismatch, refusing to install" >&2
        exit 1
    fi
    install -o root -g root -m 755 "${file}" "${KIND_BIN}"
}

function verify() {
    local kind_version kubectl_version
    kind_version=$("${KIND_BIN}" version)
    if [[ "${kind_version}" != "kind ${KIND_VERSION} "* ]]; then
        echo "unexpected kind version: ${kind_version}" >&2
        exit 1
    fi
    kubectl_version=$(kubectl version --client 2>/dev/null | awk '/Client Version/ { print $3 }')
    if [[ "${kubectl_version}" != "${KUBE_MINOR}."* ]]; then
        echo "unexpected kubectl version: ${kubectl_version:-none}" >&2
        exit 1
    fi
    if [[ $(sysctl -n fs.inotify.max_user_instances) -ne ${INOTIFY_INSTANCES} ]]; then
        echo "inotify limit not applied" >&2
        exit 1
    fi
    echo "installed kind ${KIND_VERSION} and kubectl ${kubectl_version}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
