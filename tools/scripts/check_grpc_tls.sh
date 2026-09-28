#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
VERSION="1.1.0"
FORBIDDEN_CHANNEL='grpc\.(aio\.)?insecure_channel'
FORBIDDEN_PORT='\.add_insecure_port\('
FORBIDDEN="${FORBIDDEN_CHANNEL}|${FORBIDDEN_PORT}"

function usage() {
    cat <<EOM
reject plaintext grpc calls in service source.

usage: ${SCRIPT_NAME} [file ...]

files under a grpc_gen directory, a virtualenv, or site-packages are skipped.
with no arguments every tracked python file under services/ is checked.

kubelet grpc probes only speak plaintext, so two file names get one exception each:
health.py may bind the health-only port with add_insecure_port, and
healthcheck.py may dial it with insecure_channel. every other call stays forbidden.
EOM
    exit 1
}

function main() {
    if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
        usage
    fi
    if [ "${1:-}" = "--version" ]; then
        echo "${SCRIPT_NAME} version ${VERSION}"
        exit 0
    fi

    local candidates=()
    if [ $# -gt 0 ]; then
        candidates=("$@")
    else
        mapfile -t candidates < <(git ls-files 'services/**/*.py')
    fi

    local failed=0
    local path
    local pattern
    for path in "${candidates[@]}"; do
        if is_excluded "${path}"; then
            continue
        fi
        if [ ! -f "${path}" ]; then
            continue
        fi
        pattern=$(forbidden_for "${path}")
        if grep -nE "${pattern}" "${path}" >/dev/null 2>&1; then
            echo "plaintext grpc in ${path}" >&2
            grep -nE "${pattern}" "${path}" >&2
            failed=1
        fi
    done

    if [ "${failed}" -ne 0 ]; then
        echo "use secure_channel or add_secure_port with mutual tls credentials" >&2
        exit 1
    fi
}

function forbidden_for() {
    case "$1" in
    */health.py)
        echo "${FORBIDDEN_CHANNEL}"
        ;;
    */healthcheck.py)
        echo "${FORBIDDEN_PORT}"
        ;;
    *)
        echo "${FORBIDDEN}"
        ;;
    esac
}

function is_excluded() {
    case "$1" in
    */grpc_gen/* | */.venv/* | */site-packages/*)
        return 0
        ;;
    *)
        return 1
        ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
