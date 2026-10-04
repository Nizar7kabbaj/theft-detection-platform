#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly SOURCE_FILE="${REPO_ROOT}/config/mongodb/secrets/mongo_monitor_password"
readonly TARGET_FILE="${REPO_ROOT}/config/mongodb/secrets/mongo_exporter.env"
readonly MONITOR_USER="theft_monitor"

die() {
    echo "$1" >&2
    exit 1
}

usage() {
    cat <<EOM
write the mongodb exporter env file from the monitor password secret.

usage: $(basename "$0")
EOM
    exit 1
}

main() {
    [[ $# -eq 0 ]] || usage
    [[ -s "$SOURCE_FILE" ]] || die "missing ${SOURCE_FILE}"
    local password tmp
    password="$(tr -d '\r\n' < "$SOURCE_FILE")"
    [[ "$password" != *"'"* ]] || die "monitor password holds a single quote, regenerate it"
    tmp="$(mktemp "${TARGET_FILE}.XXXXXX")"
    trap 'rm -f "$tmp"' EXIT
    chmod 600 "$tmp"
    printf "MONGODB_USER=%s\nMONGODB_PASSWORD='%s'\n" "$MONITOR_USER" "$password" > "$tmp"
    mv "$tmp" "$TARGET_FILE"
    trap - EXIT
    echo "wrote ${TARGET_FILE#"${REPO_ROOT}"/}"
}

main "$@"
