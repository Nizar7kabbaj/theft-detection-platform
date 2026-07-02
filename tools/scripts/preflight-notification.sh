#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(git)
SCRIPT_NAME=$(basename "$0")

usage() {
    cat >&2 <<EOM

sweep notification-proto consumers before rewrite

usage: ${SCRIPT_NAME} [-h|--help]

writes a grep report for every consumer of the six targets to stdout:
  torso_angle, accepted_at, alert_type, Person, Object, SendAlertReply

run from repo root. tee stdout to save the report.

example:
    ./tools/scripts/preflight-notification.sh | tee /tmp/preflight-notification.txt

EOM
    exit 1
}

exit_on_missing_tools() {
    local cmd
    for cmd in "$@"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            continue
        fi
        printf 'error: required tool %s not on PATH\n' "$cmd" >&2
        exit 1
    done
}

is_repo_root() {
    if [ ! -d .git ]; then
        printf 'error: run from repo root (.git not found in %s)\n' "$(pwd)" >&2
        return 1
    fi
    if [ ! -d proto ]; then
        printf 'error: proto/ dir not found in %s\n' "$(pwd)" >&2
        return 1
    fi
    if [ ! -d services ]; then
        printf 'error: services/ dir not found in %s\n' "$(pwd)" >&2
        return 1
    fi
    return 0
}

section() {
    local title="$1"
    printf '\n===== %s =====\n\n' "$title"
}

sweep_literal() {
    local label="$1"
    local pattern="$2"

    section "$label"

    if ! git grep -n --color=never -- "$pattern" \
        ':!services/**/grpc_gen/**' \
        ':(exclude,glob)**/*.pyc'; then
        printf '(no matches outside grpc_gen)\n'
    fi
}

sweep_word() {
    local label="$1"
    local pattern="$2"

    section "$label"

    if ! git grep -n -w --color=never -- "$pattern" \
        ':!services/**/grpc_gen/**' \
        ':(exclude,glob)**/*.pyc'; then
        printf '(no matches outside grpc_gen)\n'
    fi
}

sweep_status_enum() {
    section "STATUS_ enum values (SendAlertReply)"

    if ! git grep -n -E --color=never \
        'STATUS_(OK|FAILED|RATE_LIMITED|RETRYING|UNSPECIFIED|ACCEPTED|REJECTED|PENDING|DELIVERED)' -- \
        ':!services/**/grpc_gen/**' \
        ':(exclude,glob)**/*.pyc'; then
        printf '(no STATUS_ matches outside grpc_gen)\n'
    fi
}

sweep_generated_stubs() {
    section "generated stubs (grpc_gen) — files that mention any target"

    if ! git grep -l -E --color=never \
        'torso_angle|accepted_at|alert_type|\bPerson\b|\bObject\b|SendAlertReply' -- \
        'services/**/grpc_gen/**'; then
        printf '(none)\n'
    fi
}

print_header() {
    printf 'preflight sweep for notification-proto rewrite\n'
    printf 'repo: %s\n' "$(pwd)"
    printf 'head: %s\n' "$(git rev-parse --short HEAD)"
    printf 'branch: %s\n' "$(git rev-parse --abbrev-ref HEAD)"
    printf 'excluded: services/**/grpc_gen/**, *.pyc\n'
    printf 'gitignored paths are already excluded by git grep\n'
}

main() {
    while [ "${1:-}" != "" ]; do
        case "$1" in
        -h | --help)
            usage
            ;;
        *)
            printf 'error: unknown option %s\n' "$1" >&2
            usage
            ;;
        esac
        shift
    done

    exit_on_missing_tools "${DEPENDENCIES[@]}"
    is_repo_root || exit 1

    print_header

    sweep_literal "torso_angle" "torso_angle"
    sweep_literal "accepted_at" "accepted_at"
    sweep_literal "alert_type" "alert_type"
    sweep_word    "Person (word boundary, case sensitive)" "Person"
    sweep_word    "Object (word boundary, case sensitive)" "Object"
    sweep_word    "SendAlertReply (word boundary)" "SendAlertReply"

    sweep_status_enum
    sweep_generated_stubs

    printf '\nsweep complete\n'
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit 0
fi
