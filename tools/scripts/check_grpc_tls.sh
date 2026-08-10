#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
VERSION="1.0.0"
FORBIDDEN='grpc\.(aio\.)?insecure_channel|\.add_insecure_port\('

function usage() {
    cat <<EOM
reject plaintext grpc calls in service source.

usage: ${SCRIPT_NAME} [file ...]

files under a grpc_gen directory, a virtualenv, or site-packages are skipped.
with no arguments every tracked python file under services/ is checked.
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
    for path in "${candidates[@]}"; do
        if is_excluded "${path}"; then
            continue
        fi
        if [ ! -f "${path}" ]; then
            continue
        fi
        if grep -nE "${FORBIDDEN}" "${path}" >/dev/null 2>&1; then
            echo "plaintext grpc in ${path}" >&2
            grep -nE "${FORBIDDEN}" "${path}" >&2
            failed=1
        fi
    done

    if [ "${failed}" -ne 0 ]; then
        echo "use secure_channel or add_secure_port with mutual tls credentials" >&2
        exit 1
    fi
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
