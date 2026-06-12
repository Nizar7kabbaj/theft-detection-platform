#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(openssl)
SCRIPT_NAME=$(basename "$0")
VERSION="1.0.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CERT_DIR="${REPO_ROOT}/infrastructure/traefik/certs"
CERT_FILE="${CERT_DIR}/localhost.crt"
KEY_FILE="${CERT_DIR}/localhost.key"
VALIDITY_DAYS=365
RENEW_THRESHOLD_SECONDS=$((7 * 86400))

function usage() {
    cat <<EOM

generate a self-signed tls cert for local traefik.

usage: ${SCRIPT_NAME} [options]

options:
    -f|--force                   regenerate even if existing cert is still valid
    -h|--help                    show this help message
    --version                    show version information

dependencies: ${DEPENDENCIES[*]}

output:
    ${CERT_FILE}
    ${KEY_FILE}

cert details:
    algorithm: rsa-2048, sha-256
    validity:  ${VALIDITY_DAYS} days
    subject:   CN=localhost
    san:       DNS:localhost, DNS:*.localhost, IP:127.0.0.1

examples:
    ${SCRIPT_NAME}
    ${SCRIPT_NAME} --force

EOM
    exit 1
}

function main() {
    local force=false

    while [ $# -gt 0 ]; do
        case $1 in
        -f | --force)
            force=true
            ;;
        --version)
            echo "${SCRIPT_NAME} version ${VERSION}"
            exit 0
            ;;
        -h | --help)
            usage
            ;;
        *)
            echo "error: unknown option '$1'" >&2
            usage
            ;;
        esac
        shift
    done

    exit_on_missing_tools "${DEPENDENCIES[@]}"

    if [ "$force" = "false" ] && cert_still_valid; then
        echo "cert valid for at least 7 more days, skipping"
        return 0
    fi

    generate_cert
    echo "cert generated at ${CERT_FILE}"
}

function cert_still_valid() {
    if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
        return 1
    fi
    openssl x509 -in "${CERT_FILE}" -noout -checkend "${RENEW_THRESHOLD_SECONDS}" >/dev/null 2>&1
}

function generate_cert() {
    local tmp_key tmp_crt
    tmp_key=$(mktemp)
    tmp_crt=$(mktemp)
    trap "rm -f '${tmp_key}' '${tmp_crt}'" EXIT

    if ! openssl req -x509 -nodes \
        -newkey rsa:2048 \
        -sha256 \
        -days "${VALIDITY_DAYS}" \
        -keyout "${tmp_key}" \
        -out "${tmp_crt}" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1" \
        >/dev/null 2>&1; then
        echo "error: openssl cert generation failed" >&2
        exit 1
    fi

    mkdir -p "${CERT_DIR}"

    if ! mv "${tmp_crt}" "${CERT_FILE}"; then
        echo "error: failed to move cert to ${CERT_FILE}" >&2
        exit 1
    fi

    if ! mv "${tmp_key}" "${KEY_FILE}"; then
        echo "error: failed to move key to ${KEY_FILE}" >&2
        exit 1
    fi

    chmod 644 "${CERT_FILE}"
    chmod 600 "${KEY_FILE}"

    trap - EXIT
}

function exit_on_missing_tools() {
    for cmd in "$@"; do
        if command -v "$cmd" &>/dev/null; then
            continue
        fi
        printf "error: required tool '%s' is not installed or not in PATH\n" "$cmd" >&2
        exit 1
    done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
