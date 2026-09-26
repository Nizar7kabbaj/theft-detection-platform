#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(curl gpg awk apt-get apt-mark dpkg install)
SCRIPT_NAME=$(basename "$0")
HELM_MAJOR=v4
HELM_REPO="https://packages.buildkite.com/helm-linux/helm-debian/any/"
HELM_REPO_KEY_URL="https://packages.buildkite.com/helm-linux/helm-debian/gpgkey"
HELM_REPO_FINGERPRINT=DDF78C3E6EBB2D2CC223C95C62BA89D07698DBC6
KEYRING_DIR=/etc/apt/keyrings
KEYRING="${KEYRING_DIR}/helm-apt-keyring.gpg"
SOURCE_FILE=/etc/apt/sources.list.d/helm.sources
TMP_DIR=""

function usage() {
    cat <<EOM
install helm from the signed upstream apt repository.

usage: sudo ${SCRIPT_NAME} [options]

options:
    -h|--help    show this help

runs idempotently. pins the repository signing fingerprint and holds the package.
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
    add_repo
    install_helm
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

function add_repo() {
    local key="${TMP_DIR}/helm.key" gnupg_home="${TMP_DIR}/gnupg" fingerprint
    install -d -m 700 "${gnupg_home}"
    curl -fsSL "${HELM_REPO_KEY_URL}" -o "${key}"
    fingerprint=$(GNUPGHOME="${gnupg_home}" gpg --batch --quiet --show-keys --with-colons "${key}" \
        | awk -F: '$1 == "fpr" && !seen { print $10; seen = 1 }')
    if [[ "${fingerprint}" != "${HELM_REPO_FINGERPRINT}" ]]; then
        echo "helm apt repository fingerprint mismatch: ${fingerprint:-none}" >&2
        exit 1
    fi
    install -d -m 755 "${KEYRING_DIR}"
    GNUPGHOME="${gnupg_home}" gpg --batch --quiet --yes --dearmor --output "${KEYRING}" "${key}"
    chmod 644 "${KEYRING}"
    cat > "${SOURCE_FILE}" <<EOS
Types: deb
URIs: ${HELM_REPO}
Suites: any
Components: main
Signed-By: ${KEYRING}
EOS
    chmod 644 "${SOURCE_FILE}"
}

function install_helm() {
    apt-get update -qq
    apt-mark unhold helm >/dev/null 2>&1 || true
    apt-get install -y -qq helm >/dev/null
    apt-mark hold helm >/dev/null
}

function verify() {
    local version
    version=$(helm version --template '{{.Version}}' 2>/dev/null)
    if [[ "${version}" != "${HELM_MAJOR}."* ]]; then
        echo "unexpected helm version: ${version:-none}" >&2
        exit 1
    fi
    echo "installed helm ${version}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
