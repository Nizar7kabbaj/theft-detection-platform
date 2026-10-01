#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPENDENCIES=(docker sudo tcpdump nsenter uv)
NODE=theft-dev-worker
DURATION=35
WORK_DIR=""

function usage() {
    cat <<EOM
capture pod traffic inside a kind node and report every conversation by kind.

usage: ${SCRIPT_NAME} [options]

options:
    -n|--node NAME          node container to capture in, default ${NODE}
    -d|--duration SECONDS   capture length, default ${DURATION}
    -h|--help               show this help

needs sudo for tcpdump inside the node network namespace.
EOM
    exit 1
}

function cleanup() {
    if [[ -n "${WORK_DIR}" ]]; then
        sudo rm -rf "${WORK_DIR}"
    fi
}

function main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--node)
                [[ $# -ge 2 ]] || usage
                NODE="$2"
                shift
                ;;
            -d|--duration)
                [[ $# -ge 2 ]] || usage
                DURATION="$2"
                shift
                ;;
            -h|--help) usage ;;
            *) echo "unknown option: $1" >&2; usage ;;
        esac
        shift
    done
    for dep in "${DEPENDENCIES[@]}"; do
        command -v "${dep}" >/dev/null 2>&1 || { echo "missing dependency: ${dep}" >&2; exit 1; }
    done
    local pid pcap
    pid=$(docker inspect -f '{{.State.Pid}}' "${NODE}")
    WORK_DIR=$(mktemp -d)
    trap cleanup EXIT
    pcap="${WORK_DIR}/capture.pcap"
    sudo -v
    echo "capturing ${DURATION} s of pod tcp traffic in ${NODE}"
    sudo timeout "${DURATION}" nsenter -t "${pid}" -n \
        tcpdump -Z root -i any -nn -s 0 -U -w "${pcap}" 'tcp and net 10.244.0.0/16' 2>/dev/null || true
    sudo test -s "${pcap}" || { echo "capture produced no file at ${pcap}" >&2; exit 1; }
    uv run --no-project python "${HERE}/capture_report.py" "${pcap}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
