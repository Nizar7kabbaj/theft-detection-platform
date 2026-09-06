#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(ufw docker)
SCRIPT_NAME=$(basename "$0")
NETWORK_NAME=theft-detection-platform_observability
EXPORTER_PORT=9100
RULE_COMMENT="node exporter scrape from observability bridge"

function usage() {
    cat <<EOM
allow the observability bridge to reach node exporter on the host gateway.

usage: sudo ${SCRIPT_NAME} [options]

options:
    -h|--help    show this help

runs idempotently. safe to re-run after the docker network is recreated.
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
    local network_id bridge subnet gateway
    network_id=$(read_network_id)
    bridge="br-${network_id:0:12}"
    subnet=$(read_network_field Subnet)
    gateway=$(read_network_field Gateway)
    check_interface "${bridge}"
    drop_stale_rules
    add_rule "${bridge}" "${subnet}" "${gateway}"
    verify "${gateway}"
    echo "allowed ${subnet} to reach ${gateway}:${EXPORTER_PORT} on ${bridge}"
}

function check_deps() {
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            echo "missing dependency: ${dep}" >&2
            exit 1
        fi
    done
    if ! ufw status >/dev/null 2>&1; then
        echo "ufw is not available" >&2
        exit 1
    fi
}

function read_network_id() {
    local value
    if ! value=$(docker network inspect "${NETWORK_NAME}" --format '{{.Id}}' 2>/dev/null); then
        echo "docker network not found: ${NETWORK_NAME}" >&2
        exit 1
    fi
    echo "${value}"
}

function read_network_field() {
    local field=$1 value
    value=$(docker network inspect "${NETWORK_NAME}" \
        --format "{{range .IPAM.Config}}{{.${field}}}{{end}}")
    if [[ -z "${value}" ]]; then
        echo "network ${NETWORK_NAME} has no ${field}, pin it in compose first" >&2
        exit 1
    fi
    echo "${value}"
}

function check_interface() {
    local bridge=$1
    if ! ip link show "${bridge}" >/dev/null 2>&1; then
        echo "bridge interface not found: ${bridge}" >&2
        exit 1
    fi
}

function find_stale_rule() {
    local status
    status=$(ufw status numbered) || return 0
    echo "${status}" | grep -F "${RULE_COMMENT}" | head -1 | sed -n 's/^\[ *\([0-9]*\).*/\1/p' || true
}

function drop_stale_rules() {
    local line
    while true; do
        line=$(find_stale_rule) || true
        if [[ -z "${line}" ]]; then
            break
        fi
        ufw --force delete "${line}" >/dev/null
    done
}

function add_rule() {
    local bridge=$1 subnet=$2 gateway=$3
    ufw allow in on "${bridge}" from "${subnet}" to "${gateway}" \
        port "${EXPORTER_PORT}" proto tcp comment "${RULE_COMMENT}" >/dev/null
}

function verify() {
    local gateway=$1
    if ! ufw status | grep -q "${gateway} ${EXPORTER_PORT}/tcp"; then
        echo "rule not present after add" >&2
        exit 1
    fi
    if ! ss -ltn "sport = :${EXPORTER_PORT}" | grep -q "${gateway}:${EXPORTER_PORT}"; then
        echo "node exporter is not listening on ${gateway}:${EXPORTER_PORT}" >&2
        exit 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
