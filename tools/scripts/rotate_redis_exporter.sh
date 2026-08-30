#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly SECRET_DIR="${REPO_ROOT}/config/redis"
readonly ACL_USER="exporter"
readonly SECRET_OWNER="59000:59000"
readonly REDIS_TLS_PORT="6380"

WORK_DIR=""
INSTANCE=""
CONTAINER=""
ACL_FILE=""
OPS_FILE=""
SECRET_FILE=""
PWD_MAP_KEY=""

usage() {
    echo "usage: $(basename "$0") <stream|cache|broker>" >&2
}

cleanup() {
    if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
        find "${WORK_DIR}" -type f -exec shred -u {} + 2>/dev/null || true
        rm -rf "${WORK_DIR}"
    fi
}

die() {
    echo "$1" >&2
    exit 1
}

require_commands() {
    local cmd
    for cmd in openssl sha256sum shred docker sudo; do
        command -v "${cmd}" >/dev/null 2>&1 || die "missing command ${cmd}"
    done
}

select_instance() {
    case "$1" in
        stream)
            CONTAINER="theft-redis-stream"
            ACL_FILE="${SECRET_DIR}/redis-stream.acl"
            OPS_FILE="${SECRET_DIR}/ops_redis_password"
            SECRET_FILE="${SECRET_DIR}/stream_exporter_redis_password"
            ;;
        cache)
            CONTAINER="theft-redis"
            ACL_FILE="${SECRET_DIR}/redis.acl"
            OPS_FILE="${SECRET_DIR}/cache_ops_redis_password"
            SECRET_FILE="${SECRET_DIR}/exporter_redis_password"
            ;;
        broker)
            CONTAINER="theft-redis-broker"
            ACL_FILE="${SECRET_DIR}/redis-broker.acl"
            OPS_FILE="${SECRET_DIR}/broker_ops_redis_password"
            SECRET_FILE="${SECRET_DIR}/broker_exporter_redis_password"
            ;;
        *)
            usage
            return 1
            ;;
    esac
    INSTANCE="$1"
    PWD_MAP_KEY="rediss://${CONTAINER}:${REDIS_TLS_PORT}"
}

preflight() {
    [[ -f "${ACL_FILE}" ]] || die "acl file not found at ${ACL_FILE}"
    [[ -r "${OPS_FILE}" ]] || die "ops password not readable at ${OPS_FILE}"
    [[ "$(grep -cE "^user ${ACL_USER} " "${ACL_FILE}")" -eq 1 ]] || die "expected exactly one acl line for user ${ACL_USER}"
    docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null | grep -qx true || die "container ${CONTAINER} is not running"
}

redis_cli_as() {
    local user="$1" pw_file="$2"
    shift 2
    docker exec -i "${CONTAINER}" sh -c \
        "REDISCLI_AUTH=\$(cat) redis-cli --tls -p ${REDIS_TLS_PORT} --cert /etc/redis/tls/tls.crt --key /etc/redis/tls/tls.key --cacert /etc/redis/tls/ca.crt --user ${user} --no-auth-warning $*" < "${pw_file}"
}

main() {
    [[ $# -eq 1 ]] || { usage; return 1; }
    require_commands
    select_instance "$1" || return 1
    preflight

    WORK_DIR="$(mktemp -d)"
    chmod 700 "${WORK_DIR}"
    trap cleanup EXIT

    local secret_tmp payload_tmp acl_tmp acl_backup digest
    secret_tmp="${WORK_DIR}/secret"
    payload_tmp="${WORK_DIR}/payload"
    acl_tmp="${WORK_DIR}/acl"
    acl_backup="${WORK_DIR}/acl.backup"

    umask 077

    printf '%s' "$(openssl rand -hex 32)" > "${secret_tmp}"
    grep -qE '^[0-9a-f]{64}$' "${secret_tmp}" || die "generated password is not 64 hex characters"

    digest="$(sha256sum < "${secret_tmp}" | cut -d' ' -f1)"

    printf '{"%s":"%s"}' "${PWD_MAP_KEY}" "$(cat "${secret_tmp}")" > "${payload_tmp}"
    grep -qF "${PWD_MAP_KEY}" "${payload_tmp}" || die "password map key missing from payload"

    sed -E "/^user ${ACL_USER} /s/#[0-9a-f]{64}/#${digest}/" "${ACL_FILE}" > "${acl_tmp}"

    grep -E "^user ${ACL_USER} " "${acl_tmp}" | grep -q "#${digest}" || die "acl rewrite did not take, nothing written"
    [[ "$(wc -l < "${acl_tmp}")" -eq "$(wc -l < "${ACL_FILE}")" ]] || die "acl line count changed, nothing written"

    cp -p "${ACL_FILE}" "${acl_backup}"

    sudo install -m 600 "${payload_tmp}" "${SECRET_FILE}" || die "secret write failed, acl untouched"
    sudo chown "${SECRET_OWNER}" "${SECRET_FILE}" || die "secret chown failed, acl untouched"
    sudo grep -qF "${PWD_MAP_KEY}" "${SECRET_FILE}" || die "installed secret file does not carry the password map key"

    cat "${acl_tmp}" > "${ACL_FILE}"

    if ! redis_cli_as ops "${OPS_FILE}" ACL LOAD | grep -qx OK; then
        cat "${acl_backup}" > "${ACL_FILE}"
        die "acl load failed, acl file reverted, secret file now out of sync"
    fi

    redis_cli_as "${ACL_USER}" "${secret_tmp}" PING | grep -qx PONG || die "exporter user cannot authenticate with the new password"

    echo "rotated ${INSTANCE} exporter password, acl reloaded without restart"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
