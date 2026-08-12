#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(openssl)
SCRIPT_NAME=$(basename "$0")
VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CERT_DIR="${REPO_ROOT}/config/traefik/certs"
CA_CERT="${CERT_DIR}/ca.crt"
CA_KEY="${CERT_DIR}/ca.key"
CERT_FILE="${CERT_DIR}/localhost.crt"
KEY_FILE="${CERT_DIR}/localhost.key"
CA_VALIDITY_DAYS=3650
LEAF_VALIDITY_DAYS=365
RENEW_THRESHOLD_SECONDS=$((7 * 86400))

function usage() {
    cat <<EOM
generate a local certificate authority and a traefik leaf certificate.

usage: ${SCRIPT_NAME} [options]

options:
    -f|--force                   regenerate even if the existing leaf is still valid
    -h|--help                    show this help message
    --version                    show version information

dependencies: ${DEPENDENCIES[*]}

output:
    ${CA_CERT}
    ${CA_KEY}
    ${CERT_FILE}
    ${KEY_FILE}

cert details:
    algorithm: rsa-2048, sha-256
    ca validity:   ${CA_VALIDITY_DAYS} days
    leaf validity: ${LEAF_VALIDITY_DAYS} days
    subject:   CN=localhost
    san:       DNS:localhost, DNS:*.localhost, IP:127.0.0.1

import ${CA_CERT} into the browser trust store once. leaf renewals need no
further import.

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
    mkdir -p "${CERT_DIR}"

    if [ "$force" = "false" ] && leaf_still_valid && ca_still_valid; then
        echo "leaf valid for at least 7 more days, skipping"
        return 0
    fi

    if [ "$force" = "true" ] || ! ca_still_valid; then
        generate_ca
        echo "ca generated at ${CA_CERT}, import it into the browser trust store"
    fi

    generate_leaf
    echo "leaf generated at ${CERT_FILE}"
}

function ca_still_valid() {
    if [ ! -f "${CA_CERT}" ] || [ ! -f "${CA_KEY}" ]; then
        return 1
    fi
    openssl x509 -in "${CA_CERT}" -noout -checkend "${RENEW_THRESHOLD_SECONDS}" >/dev/null 2>&1
}

function leaf_still_valid() {
    if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
        return 1
    fi
    openssl x509 -in "${CERT_FILE}" -noout -checkend "${RENEW_THRESHOLD_SECONDS}" >/dev/null 2>&1
}

function generate_ca() {
    local tmp_key tmp_crt
    tmp_key=$(mktemp)
    tmp_crt=$(mktemp)
    trap "rm -f '${tmp_key}' '${tmp_crt}'" EXIT

    if ! openssl req -x509 -nodes \
        -newkey rsa:2048 \
        -sha256 \
        -days "${CA_VALIDITY_DAYS}" \
        -keyout "${tmp_key}" \
        -out "${tmp_crt}" \
        -subj "/CN=theft-detection-platform local ca" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        >/dev/null 2>&1; then
        echo "error: openssl ca generation failed" >&2
        exit 1
    fi

    mv "${tmp_crt}" "${CA_CERT}"
    mv "${tmp_key}" "${CA_KEY}"
    chmod 644 "${CA_CERT}"
    chmod 600 "${CA_KEY}"
    trap - EXIT
}

function generate_leaf() {
    local tmp_key tmp_csr tmp_crt tmp_ext
    tmp_key=$(mktemp)
    tmp_csr=$(mktemp)
    tmp_crt=$(mktemp)
    tmp_ext=$(mktemp)
    trap "rm -f '${tmp_key}' '${tmp_csr}' '${tmp_crt}' '${tmp_ext}'" EXIT

    cat >"${tmp_ext}" <<'EOM'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1
EOM

    if ! openssl req -nodes -new \
        -newkey rsa:2048 \
        -sha256 \
        -keyout "${tmp_key}" \
        -out "${tmp_csr}" \
        -subj "/CN=localhost" \
        >/dev/null 2>&1; then
        echo "error: openssl leaf request failed" >&2
        exit 1
    fi

    if ! openssl x509 -req \
        -in "${tmp_csr}" \
        -CA "${CA_CERT}" \
        -CAkey "${CA_KEY}" \
        -CAcreateserial \
        -sha256 \
        -days "${LEAF_VALIDITY_DAYS}" \
        -extfile "${tmp_ext}" \
        -out "${tmp_crt}" \
        >/dev/null 2>&1; then
        echo "error: openssl leaf signing failed" >&2
        exit 1
    fi

    mv "${tmp_crt}" "${CERT_FILE}"
    mv "${tmp_key}" "${KEY_FILE}"
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
