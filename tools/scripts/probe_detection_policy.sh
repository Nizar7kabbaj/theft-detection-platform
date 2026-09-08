#!/usr/bin/env bash
set -euo pipefail

readonly AUTH_URL="http://127.0.0.1:8002"
readonly API_URL="http://127.0.0.1:8001"
readonly PASSWORD_FILE="config/auth/test_users_password"
readonly ACCESS_COOKIE="__Host-access_token"
readonly CSRF_COOKIE="__Host-csrf"

headers_file=""
access=""
csrf=""

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

login() {
    local username="$1"
    local password status
    password="$(tr -d '\n' < "${PASSWORD_FILE}")"
    headers_file="$(mktemp)"
    chmod 600 "${headers_file}"
    status="$(curl -s -o /dev/null -w '%{http_code}' \
        -D "${headers_file}" \
        -X POST "${AUTH_URL}/auth/login" \
        -H 'Content-Type: application/json' \
        --data-binary @<(printf '{"username":"%s","password":"%s"}' "${username}" "${password}"))"
    unset password
    [[ "${status}" == "200" ]] || die "login failed user=${username} status=${status}"
    access="$(read_cookie "${ACCESS_COOKIE}")"
    csrf="$(read_cookie "${CSRF_COOKIE}")"
    [[ -n "${access}" && -n "${csrf}" ]] || die "cookies not returned for ${username}"
}

call() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-s -w '\n%{http_code}' -X "${method}" "${API_URL}${path}"
        -H "Cookie: ${ACCESS_COOKIE}=${access}; ${CSRF_COOKIE}=${csrf}"
        -H "X-CSRF-Token: ${csrf}"
        -H 'Content-Type: application/json')
    if [[ -n "${body}" ]]; then
        args+=(-d "${body}")
    fi
    curl "${args[@]}"
}

report() {
    local label="$1" expected="$2" response="$3"
    local status body
    status="$(tail -n 1 <<< "${response}")"
    body="$(sed '$d' <<< "${response}")"
    if [[ "${status}" == "${expected}" ]]; then
        echo "ok    ${label} ${status}"
    else
        echo "FAIL  ${label} expected ${expected} got ${status}"
    fi
    echo "      ${body:0:220}"
}

main() {
    [[ -f "${PASSWORD_FILE}" ]] || die "password file not found: ${PASSWORD_FILE}"

    login "ws-admin"
    local current version
    current="$(call GET /api/v1/policy/detection)"
    report "admin read" 200 "${current}"
    version="$(sed '$d' <<< "${current}" | grep -oE '"version":[0-9]+' | head -n 1 | cut -d: -f2)"
    [[ -n "${version}" ]] || die "could not read version from policy response"
    echo "      live version ${version}"

    report "out of range" 422 "$(call PUT /api/v1/policy/detection \
        "{\"expected_version\":${version},\"policy\":{\"concealment\":{\"grab_ratio\":99}}}")"

    report "unknown field" 422 "$(call PUT /api/v1/policy/detection \
        "{\"expected_version\":${version},\"policy\":{\"concealment\":{\"grab_ratioo\":0.7}}}")"

    report "stale version" 409 "$(call PUT /api/v1/policy/detection \
        "{\"expected_version\":$((version + 5)),\"policy\":{\"concealment\":{\"grab_ratio\":0.65}}}")"

    report "admin write" 200 "$(call PUT /api/v1/policy/detection \
        "{\"expected_version\":${version},\"policy\":{\"concealment\":{\"grab_ratio\":0.55}}}")"

    report "history" 200 "$(call GET /api/v1/policy/detection/history)"

    login "ws-operator"
    report "operator read" 200 "$(call GET /api/v1/policy/detection)"
    report "operator write" 403 "$(call PUT /api/v1/policy/detection \
        "{\"expected_version\":$((version + 1)),\"policy\":{\"concealment\":{\"grab_ratio\":0.5}}}")"

    login "ws-viewer"
    report "viewer read" 403 "$(call GET /api/v1/policy/detection)"
}

main "$@"
