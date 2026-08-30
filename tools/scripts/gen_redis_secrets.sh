#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly SECRET_DIR="${REPO_ROOT}/config/redis"
readonly EXPORTER_OWNER="59000:59000"

readonly OWNED_BY_EXPORTER=(
    "broker_exporter_redis_password"
    "broker_ops_redis_password"
    "exporter_redis_password"
    "stream_exporter_redis_password"
)

readonly SECRET_FILES=(
    "ai_redis_password"
    "api_redis_password"
    "audit_redis_password"
    "auth_redis_password"
    "broker_exporter_redis_password"
    "broker_ops_redis_password"
    "broker_redis_password"
    "cache_ops_redis_password"
    "camera_redis_password"
    "exporter_redis_password"
    "gate_redis_password"
    "notify_redis_password"
    "ops_redis_password"
    "stream_exporter_redis_password"
    "stream_reader_redis_password"
)

die() {
    echo "$1" >&2
    exit 1
}

require_commands() {
    local cmd
    for cmd in openssl sha256sum sudo; do
        command -v "${cmd}" >/dev/null 2>&1 || die "missing command ${cmd}"
    done
}

is_exporter_owned() {
    local name="$1" candidate
    for candidate in "${OWNED_BY_EXPORTER[@]}"; do
        if [[ "${candidate}" == "${name}" ]]; then
            return 0
        fi
    done
    return 1
}

create_secret() {
    local name="$1" path="${SECRET_DIR}/$1"
    if [[ -e "${path}" ]]; then
        echo "present ${name}"
        return 0
    fi
    local digest
    (umask 077; printf '%s' "$(openssl rand -hex 32)" > "${path}")
    digest="$(sha256sum < "${path}" | cut -d' ' -f1)"
    if is_exporter_owned "${name}"; then
        sudo chown "${EXPORTER_OWNER}" "${path}" || die "chown failed for ${name}"
    fi
    printf 'created %s digest %s\n' "${name}" "${digest}"
}

main() {
    require_commands
    [[ -d "${SECRET_DIR}" ]] || die "secret directory not found at ${SECRET_DIR}"
    local name
    for name in "${SECRET_FILES[@]}"; do
        create_secret "${name}"
    done
    echo "digests above belong on the matching acl or conf line for each user"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
