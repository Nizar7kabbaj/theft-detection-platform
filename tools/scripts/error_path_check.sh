#!/usr/bin/env bash
set -euo pipefail

base_url="${BASE_URL:-https://localhost}"
ca_cert="config/traefik/certs/ca.crt"
passed=0
failed=0

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

request() {
  local expected="$1"
  local label="$2"
  shift 2
  local code
  code="$(curl -sS --cacert "${ca_cert}" -o "${work_dir}/body" -w '%{http_code}' "$@")" || {
    printf 'error  %s: request failed\n' "${label}" >&2
    failed=$((failed + 1))
    return 0
  }
  if [[ "${code}" == "${expected}" ]]; then
    printf 'pass   %s (%s)\n' "${label}" "${code}"
    passed=$((passed + 1))
    return 0
  fi
  printf 'fail   %s: expected %s got %s\n' "${label}" "${expected}" "${code}" >&2
  failed=$((failed + 1))
}

body_contains() {
  local needle="$1"
  local label="$2"
  if grep -qF "${needle}" "${work_dir}/body"; then
    printf 'pass   %s\n' "${label}"
    passed=$((passed + 1))
    return 0
  fi
  printf 'fail   %s: marker not found\n' "${label}" >&2
  failed=$((failed + 1))
}

main() {
  if [[ ! -f "${ca_cert}" ]]; then
    printf 'error: ca certificate not found at %s\n' "${ca_cert}" >&2
    exit 1
  fi

  head -c 20000 /dev/zero | tr '\0' 'a' > "${work_dir}/oversize.txt"
  printf '{"digest":"%s","path":"/dashboard"}' "$(cat "${work_dir}/oversize.txt")" \
    > "${work_dir}/oversize.json"
  printf '{"digest":"abc123","path":"/dashboard"}' > "${work_dir}/valid.json"
  printf 'not json at all' > "${work_dir}/broken.json"
  printf '{"csp-report":{"violated-directive":"script-src"}}' > "${work_dir}/report.json"

  request 204 "client-error accepts a same-origin report" \
    -X POST "${base_url}/client-error" \
    -H 'Content-Type: application/json' \
    -H "Origin: ${base_url}" \
    --data-binary "@${work_dir}/valid.json"

  request 403 "client-error refuses a cross-origin report" \
    -X POST "${base_url}/client-error" \
    -H 'Content-Type: application/json' \
    -H 'Origin: https://evil.example' \
    --data-binary "@${work_dir}/valid.json"

  request 400 "client-error refuses malformed json" \
    -X POST "${base_url}/client-error" \
    -H 'Content-Type: application/json' \
    -H "Origin: ${base_url}" \
    --data-binary "@${work_dir}/broken.json"

  request 413 "client-error caps a chunked body with no declared length" \
    -X POST "${base_url}/client-error" \
    -H 'Content-Type: application/json' \
    -H "Origin: ${base_url}" \
    -H 'Transfer-Encoding: chunked' \
    --data-binary "@${work_dir}/oversize.json"

  request 204 "csp-report accepts a violation report" \
    -X POST "${base_url}/csp-report" \
    -H 'Content-Type: application/csp-report' \
    --data-binary "@${work_dir}/report.json"

  request 413 "csp-report caps a chunked body with no declared length" \
    -X POST "${base_url}/csp-report" \
    -H 'Content-Type: application/json' \
    -H 'Transfer-Encoding: chunked' \
    --data-binary "@${work_dir}/oversize.json"

  request 200 "healthz answers for the reachability probe" "${base_url}/healthz"
  body_contains '"status":"ok"' "healthz returns the expected payload"


  printf '\n%d passed, %d failed\n' "${passed}" "${failed}"
  if ((failed > 0)); then
    exit 1
  fi
}

main "$@"
