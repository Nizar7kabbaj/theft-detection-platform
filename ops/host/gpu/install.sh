#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(nvidia-smi systemctl)
SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HELPER_SRC="${SCRIPT_DIR}/gpu-clock-lock"
UNIT_SRC="${SCRIPT_DIR}/gpu-clock-lock.service"
HELPER_DST=/usr/local/sbin/gpu-clock-lock
UNIT_DST=/etc/systemd/system/gpu-clock-lock.service

function usage() {
    cat <<EOM

install the gpu clock lock helper and systemd unit.

usage: sudo ${SCRIPT_NAME} [options]

options:
    -h|--help    show this help

runs idempotently. safe to re-run after editing the helper or unit.

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
    check_sources
    install_files
    enable_service
    verify
    echo "installed and active"
}

function check_deps() {
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            echo "missing dependency: ${dep}" >&2
            exit 1
        fi
    done
}

function check_sources() {
    if [[ ! -f "${HELPER_SRC}" ]]; then
        echo "helper source not found: ${HELPER_SRC}" >&2
        exit 1
    fi
    if [[ ! -f "${UNIT_SRC}" ]]; then
        echo "unit source not found: ${UNIT_SRC}" >&2
        exit 1
    fi
}

function install_files() {
    install -o root -g root -m 0755 "${HELPER_SRC}" "${HELPER_DST}"
    install -o root -g root -m 0644 "${UNIT_SRC}" "${UNIT_DST}"
}

function enable_service() {
    systemctl daemon-reload
    systemctl enable --now gpu-clock-lock.service
}

function verify() {
    if ! systemctl is-active --quiet gpu-clock-lock.service; then
        echo "gpu-clock-lock.service failed to activate" >&2
        systemctl status gpu-clock-lock.service --no-pager >&2 || true
        exit 1
    fi

    local pm_state
    pm_state=$(nvidia-smi --query-gpu=persistence_mode --format=csv,noheader | tr -d ' ')
    if [[ "${pm_state}" != "Enabled" ]]; then
        echo "install completed but persistence mode is ${pm_state}" >&2
        exit 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
