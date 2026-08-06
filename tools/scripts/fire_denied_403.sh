#!/usr/bin/env bash
set -euo pipefail

readonly AUTH_URL="http://127.0.0.1:8002"
readonly API_URL="http://127.0.0.1:8001"
readonly USERNAME="ws-viewer"
readonly PASSWORD_FILE="config/auth/test_users_password"
readonly ACCESS_COOKIE="__Host-access_token"
readonly CSRF_COOKIE="__Host-csrf"

headers_file=""

cleanup() {
    if [[ -n "${headers_file}" && -f "${headers_file}" ]]; then
        shred -u "${headers_file}" 2>/dev/null || rm -f "${headers_file}"
    fi
}
trap cleanup EXIT

die() {
    echo "$1" >&2
    exit 1
}

read_cookie() {
    local name="$1"
    grep -i '^set-cookie:' "${headers_file}" \
        | sed -n "s/.*${name}=\([^;]*\).*/\1/p" \
        | head -n 1
}

main() {
    [[ -f "${PASSWORD_FILE}" ]] || die "password file not found: ${PASSWORD_FILE}"

    local password
    password="$(tr -d '\n' < "${PASSWORD_FILE}")"

    headers_file="$(mktemp)"
    chmod 600 "${headers_file}"

    local login_status
    login_status="$(curl -s -o /dev/null -w '%{http_code}' \
        -D "${headers_file}" \
        -X POST "${AUTH_URL}/auth/login" \
        -H 'Content-Type: application/json' \
        --data-binary @<(printf '{"username":"%s","password":"%s"}' "${USERNAME}" "${password}"))"

    unset password

    if [[ "${login_status}" != "200" ]]; then
        die "login failed status=${login_status}"
    fi

    local access csrf
    access="$(read_cookie "${ACCESS_COOKIE}")"
    csrf="$(read_cookie "${CSRF_COOKIE}")"

    [[ -n "${access}" ]] || die "access cookie not returned"
    [[ -n "${csrf}" ]] || die "csrf cookie not returned"

    echo "login ok, cookies captured"

    local response
    response="$(curl -s -w '\n%{http_code}' \
        -X POST "${API_URL}/api/v1/cameras" \
        -H "Cookie: ${ACCESS_COOKIE}=${access}; ${CSRF_COOKIE}=${csrf}" \
        -H "X-CSRF-Token: ${csrf}" \
        -H 'Content-Type: application/json' \
        -d '{"name":"denial-probe","rtsp_url":"rtsp://127.0.0.1:8554/probe"}')"

    local status body
    status="$(tail -n 1 <<< "${response}")"
    body="$(sed '$d' <<< "${response}")"

    echo "status ${status}"
    echo "body ${body}"
}

main "$@"
