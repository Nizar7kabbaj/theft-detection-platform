#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(openssl cmp install)
SCRIPT_NAME=$(basename "$0")
VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MESH_DIR="${REPO_ROOT}/config/pki/mesh-ca"
ROOT_CERT="${MESH_DIR}/root-cert.pem"
ROOT_KEY="${MESH_DIR}/root-key.pem"
ISTIOD_DIR="${MESH_DIR}/istiod"
ORG="theft-detection-platform"
CURVE="P-256"
ROOT_VALIDITY_DAYS=3650
INTERMEDIATE_VALIDITY_DAYS=365
INTERMEDIATE_RENEW_SECONDS=$((30 * 86400))
ISTIOD_SAN="istiod.istio-system.svc"
TMP_FILES=()

function usage() {
    cat <<EOM
generate the mesh root and the istiod intermediate used as the istio plugged-in ca.

usage: ${SCRIPT_NAME} [options]

options:
    -f|--force    reissue the istiod intermediate even when it is still valid
    -h|--help     show this help message
    --version     show version information

dependencies: ${DEPENDENCIES[*]}

output:
    ${ROOT_CERT}
    ${ROOT_KEY}                 passphrase protected, never leaves this machine
    ${ISTIOD_DIR}/ca-cert.pem
    ${ISTIOD_DIR}/ca-key.pem
    ${ISTIOD_DIR}/cert-chain.pem
    ${ISTIOD_DIR}/root-cert.pem

certificate details:
    algorithm:     ecdsa ${CURVE}, sha-256
    root:          ${ROOT_VALIDITY_DAYS} days, path length 1, key encrypted with aes-256-cbc
    intermediate:  ${INTERMEDIATE_VALIDITY_DAYS} days, path length 0, san dns ${ISTIOD_SAN}
    renewal:       intermediate reissued when less than $((INTERMEDIATE_RENEW_SECONDS / 86400)) days remain

the root is created once. the passphrase is asked when the root is created
and every time the intermediate is signed.

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
    umask 077
    trap cleanup EXIT

    ensure_root
    ensure_intermediate "${force}"
}

function cleanup() {
    if [ ${#TMP_FILES[@]} -gt 0 ]; then
        rm -f "${TMP_FILES[@]}"
    fi
}

function new_tmp() {
    local -n target="$1"
    target=$(mktemp -p "$2" ".tmp.XXXXXX")
    TMP_FILES+=("${target}")
}

function cert_still_valid() {
    local cert_file="$1"
    local key_file="$2"
    local seconds="$3"
    if [ ! -f "${cert_file}" ] || [ ! -f "${key_file}" ]; then
        return 1
    fi
    openssl x509 -in "${cert_file}" -noout -checkend "${seconds}" >/dev/null 2>&1
}

function ensure_root() {
    if [ -f "${ROOT_CERT}" ] && [ -f "${ROOT_KEY}" ]; then
        echo "mesh root present, $(openssl x509 -in "${ROOT_CERT}" -noout -enddate)"
        return 0
    fi

    if [ -f "${ROOT_CERT}" ] || [ -f "${ROOT_KEY}" ]; then
        echo "error: only one of root-cert.pem and root-key.pem exists in ${MESH_DIR}" >&2
        exit 1
    fi

    install -d -m 700 "${MESH_DIR}"

    local tmp_key tmp_crt
    new_tmp tmp_key "${MESH_DIR}"
    new_tmp tmp_crt "${MESH_DIR}"

    echo "creating the mesh root, choose a passphrase for its key" >&2

    if ! openssl genpkey \
        -algorithm EC \
        -pkeyopt "ec_paramgen_curve:${CURVE}" \
        -pkeyopt ec_param_enc:named_curve \
        -aes-256-cbc \
        -out "${tmp_key}"; then
        echo "error: root key generation failed" >&2
        exit 1
    fi

    echo "self-signing the mesh root, enter the same passphrase" >&2

    if ! openssl req -x509 -new \
        -key "${tmp_key}" \
        -sha256 \
        -days "${ROOT_VALIDITY_DAYS}" \
        -subj "/O=${ORG}/CN=${ORG} mesh root ca" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -out "${tmp_crt}"; then
        echo "error: root certificate generation failed" >&2
        exit 1
    fi

    mv "${tmp_crt}" "${ROOT_CERT}"
    mv "${tmp_key}" "${ROOT_KEY}"
    chmod 644 "${ROOT_CERT}"
    chmod 600 "${ROOT_KEY}"
    echo "mesh root generated at ${ROOT_CERT}"
}

function ensure_intermediate() {
    local force="$1"

    if [ "${force}" = "false" ] &&
        cert_still_valid "${ISTIOD_DIR}/ca-cert.pem" "${ISTIOD_DIR}/ca-key.pem" "${INTERMEDIATE_RENEW_SECONDS}" &&
        openssl verify -CAfile "${ROOT_CERT}" "${ISTIOD_DIR}/ca-cert.pem" >/dev/null 2>&1 &&
        cmp -s "${ROOT_CERT}" "${ISTIOD_DIR}/root-cert.pem"; then
        echo "istiod intermediate valid, skipping"
        return 0
    fi

    if ! openssl x509 -in "${ROOT_CERT}" -noout -checkend "$((INTERMEDIATE_VALIDITY_DAYS * 86400))" >/dev/null 2>&1; then
        echo "error: the mesh root expires before a new intermediate would, rotate the root first" >&2
        exit 1
    fi

    install -d -m 700 "${ISTIOD_DIR}"

    local tmp_key tmp_csr tmp_crt tmp_ext serial
    new_tmp tmp_key "${ISTIOD_DIR}"
    new_tmp tmp_csr "${ISTIOD_DIR}"
    new_tmp tmp_crt "${ISTIOD_DIR}"
    new_tmp tmp_ext "${ISTIOD_DIR}"

    if ! openssl genpkey \
        -algorithm EC \
        -pkeyopt "ec_paramgen_curve:${CURVE}" \
        -pkeyopt ec_param_enc:named_curve \
        -out "${tmp_key}" >/dev/null 2>&1; then
        echo "error: intermediate key generation failed" >&2
        exit 1
    fi

    if ! openssl req -new \
        -key "${tmp_key}" \
        -sha256 \
        -subj "/O=${ORG}/CN=istiod intermediate ca" \
        -out "${tmp_csr}" >/dev/null 2>&1; then
        echo "error: intermediate csr generation failed" >&2
        exit 1
    fi

    cat >"${tmp_ext}" <<EOM
basicConstraints=critical,CA:TRUE,pathlen:0
keyUsage=critical,digitalSignature,keyCertSign,cRLSign
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always
subjectAltName=DNS:${ISTIOD_SAN}
EOM

    serial=$(openssl rand -hex 16)

    echo "signing the istiod intermediate, enter the mesh root passphrase" >&2

    if ! openssl x509 -req \
        -in "${tmp_csr}" \
        -CA "${ROOT_CERT}" \
        -CAkey "${ROOT_KEY}" \
        -set_serial "0x${serial}" \
        -days "${INTERMEDIATE_VALIDITY_DAYS}" \
        -sha256 \
        -extfile "${tmp_ext}" \
        -out "${tmp_crt}"; then
        echo "error: intermediate signing failed" >&2
        exit 1
    fi

    if ! openssl verify -CAfile "${ROOT_CERT}" "${tmp_crt}" >/dev/null 2>&1; then
        echo "error: intermediate does not verify against the mesh root" >&2
        exit 1
    fi

    mv "${tmp_crt}" "${ISTIOD_DIR}/ca-cert.pem"
    mv "${tmp_key}" "${ISTIOD_DIR}/ca-key.pem"
    cp "${ROOT_CERT}" "${ISTIOD_DIR}/root-cert.pem"
    cat "${ISTIOD_DIR}/ca-cert.pem" "${ROOT_CERT}" >"${ISTIOD_DIR}/cert-chain.pem"
    chmod 644 "${ISTIOD_DIR}/ca-cert.pem" "${ISTIOD_DIR}/root-cert.pem" "${ISTIOD_DIR}/cert-chain.pem"
    chmod 600 "${ISTIOD_DIR}/ca-key.pem"
    echo "istiod intermediate generated at ${ISTIOD_DIR}"
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
