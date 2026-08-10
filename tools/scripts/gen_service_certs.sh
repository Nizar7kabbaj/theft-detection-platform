#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(openssl)
SCRIPT_NAME=$(basename "$0")
VERSION="1.1.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PKI_DIR="${REPO_ROOT}/config/pki"
CA_DIR="${PKI_DIR}/ca"
CA_CERT="${CA_DIR}/ca.crt"
CA_KEY="${CA_DIR}/ca.key"
TRUST_DOMAIN="theft-detection-platform"
CURVE="P-256"
CA_VALIDITY_DAYS=3650
LEAF_VALIDITY_DAYS=90
RENEW_THRESHOLD_SECONDS=$((14 * 86400))
SERVER_KEY_GROUP="redis-conf"
SERVICES=(api auth ai camera detect-gate notification audit redis redis-broker redis-stream exporter)

function usage() {
    cat <<EOM
generate a local certificate authority and per-service certificates.

usage: ${SCRIPT_NAME} [options]

options:
    -s|--service NAME    generate one service only, repeatable
    -f|--force           regenerate even when the existing certificate is still valid
    -h|--help            show this help message
    --version            show version information

dependencies: ${DEPENDENCIES[*]}

output:
    ${CA_DIR}/ca.crt
    ${CA_DIR}/ca.key
    ${PKI_DIR}/<service>/tls.crt
    ${PKI_DIR}/<service>/tls.key

certificate details:
    algorithm:  ecdsa ${CURVE}, sha-256
    ca:         ${CA_VALIDITY_DAYS} days, path length 0
    leaf:       ${LEAF_VALIDITY_DAYS} days
    identity:   spiffe://${TRUST_DOMAIN}/service/<name> as a uri subject alternative name

datastore keys are owned by group ${SERVER_KEY_GROUP} at mode 640 so the
server process can read them without the key becoming world readable.

services: ${SERVICES[*]}

examples:
    ${SCRIPT_NAME}
    ${SCRIPT_NAME} --service redis --force
EOM
    exit 1
}

function main() {
    local force=false
    local selected=()

    while [ $# -gt 0 ]; do
        case $1 in
        -s | --service)
            if [ $# -lt 2 ]; then
                echo "error: --service requires a name" >&2
                usage
            fi
            selected+=("$2")
            shift
            ;;
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

    if [ ${#selected[@]} -eq 0 ]; then
        selected=("${SERVICES[@]}")
    fi

    local name
    for name in "${selected[@]}"; do
        if ! is_known_service "${name}"; then
            echo "error: unknown service '${name}'" >&2
            exit 1
        fi
    done

    for name in "${selected[@]}"; do
        if needs_group_readable_key "${name}"; then
            exit_on_missing_group "${SERVER_KEY_GROUP}"
            break
        fi
    done

    ensure_ca "${force}"

    for name in "${selected[@]}"; do
        ensure_leaf "${name}" "${force}"
    done
}

function is_known_service() {
    local candidate="$1"
    local known
    for known in "${SERVICES[@]}"; do
        if [ "${known}" = "${candidate}" ]; then
            return 0
        fi
    done
    return 1
}

function is_server_service() {
    case "$1" in
    audit | ai | auth | notification | redis | redis-broker | redis-stream)
        return 0
        ;;
    *)
        return 1
        ;;
    esac
}

function needs_group_readable_key() {
    case "$1" in
    redis | redis-broker | redis-stream)
        return 0
        ;;
    *)
        return 1
        ;;
    esac
}

function service_dns_names() {
    case "$1" in
    redis)
        echo "redis theft-redis"
        ;;
    redis-broker)
        echo "redis-broker theft-redis-broker"
        ;;
    redis-stream)
        echo "redis-stream theft-redis-stream"
        ;;
    *)
        echo "$1"
        ;;
    esac
}

function cert_still_valid() {
    local cert_file="$1"
    local key_file="$2"
    if [ ! -f "${cert_file}" ] || [ ! -f "${key_file}" ]; then
        return 1
    fi
    openssl x509 -in "${cert_file}" -noout -checkend "${RENEW_THRESHOLD_SECONDS}" >/dev/null 2>&1
}

function ensure_ca() {
    local force="$1"

    if [ "${force}" = "false" ] && cert_still_valid "${CA_CERT}" "${CA_KEY}"; then
        echo "ca valid, skipping"
        return 0
    fi

    local tmp_key tmp_crt
    tmp_key=$(mktemp)
    tmp_crt=$(mktemp)
    trap "rm -f '${tmp_key}' '${tmp_crt}'" EXIT

    if ! openssl req -x509 -noenc \
        -newkey ec \
        -pkeyopt "ec_paramgen_curve:${CURVE}" \
        -sha256 \
        -days "${CA_VALIDITY_DAYS}" \
        -keyout "${tmp_key}" \
        -out "${tmp_crt}" \
        -subj "/CN=${TRUST_DOMAIN} local ca" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        >/dev/null 2>&1; then
        echo "error: ca generation failed" >&2
        exit 1
    fi

    mkdir -p "${CA_DIR}"
    mv "${tmp_crt}" "${CA_CERT}"
    mv "${tmp_key}" "${CA_KEY}"
    chmod 644 "${CA_CERT}"
    chmod 600 "${CA_KEY}"
    trap - EXIT
    echo "ca generated at ${CA_CERT}"
}

function ensure_leaf() {
    local name="$1"
    local force="$2"
    local service_dir="${PKI_DIR}/${name}"
    local cert_file="${service_dir}/tls.crt"
    local key_file="${service_dir}/tls.key"

    if [ "${force}" = "false" ] && cert_still_valid "${cert_file}" "${key_file}"; then
        echo "${name} certificate valid, skipping"
        return 0
    fi

    local tmp_key tmp_csr tmp_crt tmp_ext serial
    tmp_key=$(mktemp)
    tmp_csr=$(mktemp)
    tmp_crt=$(mktemp)
    tmp_ext=$(mktemp)
    trap "rm -f '${tmp_key}' '${tmp_csr}' '${tmp_crt}' '${tmp_ext}'" EXIT

    local san="URI:spiffe://${TRUST_DOMAIN}/service/${name}"
    local eku="clientAuth"

    if is_server_service "${name}"; then
        local dns
        for dns in $(service_dns_names "${name}"); do
            san="${san},DNS:${dns}"
        done
        san="${san},DNS:localhost,IP:127.0.0.1"
        eku="serverAuth,clientAuth"
    fi

    cat >"${tmp_ext}" <<EOM
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=${eku}
subjectAltName=${san}
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always
EOM

    if ! openssl req -new -noenc \
        -newkey ec \
        -pkeyopt "ec_paramgen_curve:${CURVE}" \
        -sha256 \
        -keyout "${tmp_key}" \
        -out "${tmp_csr}" \
        -subj "/CN=${name}" \
        >/dev/null 2>&1; then
        echo "error: csr generation failed for ${name}" >&2
        exit 1
    fi

    serial=$(openssl rand -hex 16)

    if ! openssl x509 -req \
        -in "${tmp_csr}" \
        -CA "${CA_CERT}" \
        -CAkey "${CA_KEY}" \
        -set_serial "0x${serial}" \
        -days "${LEAF_VALIDITY_DAYS}" \
        -sha256 \
        -extfile "${tmp_ext}" \
        -out "${tmp_crt}" \
        >/dev/null 2>&1; then
        echo "error: signing failed for ${name}" >&2
        exit 1
    fi

    mkdir -p "${service_dir}"
    mv "${tmp_crt}" "${cert_file}"
    mv "${tmp_key}" "${key_file}"
    rm -f "${tmp_csr}" "${tmp_ext}"
    chmod 644 "${cert_file}"

    if needs_group_readable_key "${name}"; then
        chgrp "${SERVER_KEY_GROUP}" "${key_file}"
        chmod 640 "${key_file}"
    else
        chmod 600 "${key_file}"
    fi

    trap - EXIT
    echo "${name} certificate generated at ${cert_file}"
}

function exit_on_missing_group() {
    local group="$1"
    if getent group "${group}" >/dev/null 2>&1; then
        return 0
    fi
    printf "error: group '%s' does not exist, datastore keys cannot be made readable to the server\n" "${group}" >&2
    exit 1
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
