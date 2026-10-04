#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT

readonly SECRETS=(
    "config/mongodb/secrets/mongo_root_password 640 mongo-cert"
    "config/mongodb/secrets/mongo_api_password 640 mongo-cert"
    "config/mongodb/secrets/mongo_notification_password 640 mongo-cert"
    "config/mongodb/secrets/mongo_monitor_password 640 mongo-cert"
    "config/mongodb/tls/mongod.pem 640 mongo-cert"
    "config/mongodb/secrets/mongo_exporter.env 600 -"
    "config/grafana/admin_password 640 grafana-conf"
    "config/alertmanager/webhook_token 640 alertmanager-conf"
    "services/api/.env 600 -"
    "services/notification/.env 600 -"
)

die() {
    echo "$1" >&2
    exit 1
}

usage() {
    cat <<EOM
set or check mode and group on host secret files.

usage: $(basename "$0") [--check]

--check reports drift and exits 1 without changing anything.
a group of - keeps the owner's group.
EOM
    exit 1
}

main() {
    local check=false
    case "${1:-}" in
        "") ;;
        --check) check=true ;;
        *) usage ;;
    esac
    local entry path mode group full drift=0
    for entry in "${SECRETS[@]}"; do
        read -r path mode group <<<"$entry"
        full="${REPO_ROOT}/${path}"
        [[ -f "$full" ]] || die "missing ${path}"
        if [[ "$group" != "-" ]]; then
            getent group "$group" >/dev/null || die "host group ${group} does not exist"
        fi
        if [[ "$(stat -c '%a' "$full")" == "$mode" ]] \
            && { [[ "$group" == "-" ]] || [[ "$(stat -c '%G' "$full")" == "$group" ]]; }; then
            continue
        fi
        if [[ "$check" == true ]]; then
            echo "drift ${path}: $(stat -c '%a %G' "$full"), want ${mode} ${group}"
            drift=1
            continue
        fi
        if [[ "$group" != "-" ]]; then
            chgrp "$group" "$full"
        fi
        chmod "$mode" "$full"
        echo "fixed ${path}: ${mode} ${group}"
    done
    [[ "$drift" -eq 0 ]] || exit 1
    echo "secret files ok"
}

main "$@"
