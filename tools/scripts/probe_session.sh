#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://localhost}"
LOGIN_PATH="/auth/login"
PROBE_PATH="/api/v1/alerts/count"
REFRESH_PATH="/auth/refresh"

die() {
  echo "$1" >&2
  exit 1
}

JAR="$(mktemp)"
chmod 600 "$JAR"
cleanup() {
  shred -u "$JAR" 2>/dev/null || rm -f "$JAR"
}
trap cleanup EXIT

stamp() {
  date -u +%H:%M:%S
}

call() {
  local path="$1"
  curl -k -s -o /dev/null -w "%{http_code}" \
    -b "$JAR" -c "$JAR" \
    "${BASE}${path}"
}

show_jar() {
  local now
  now="$(date +%s)"
  while read -r _ _ _ _ expiry name _; do
    if [ -z "${name:-}" ]; then
      continue
    fi
    if [ "$expiry" = "0" ]; then
      echo "  ${name} session-only"
      continue
    fi
    echo "  ${name} expires in $(( expiry - now ))s"
  done < <(grep -v '^#' "$JAR" | grep -v '^$')
}

read -rp "username: " USERNAME
read -rsp "password: " PASSWORD
echo

status="$(curl -k -s -o /dev/null -w "%{http_code}" \
  -c "$JAR" \
  -H "content-type: application/json" \
  -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" \
  "${BASE}${LOGIN_PATH}")"
unset PASSWORD

if [ "$status" != "200" ]; then
  die "login returned ${status}"
fi

echo "$(stamp) login ok"
show_jar

INTERVAL="${INTERVAL:-120}"
ROUNDS="${ROUNDS:-10}"

for i in $(seq 1 "$ROUNDS"); do
  probe="$(call "$PROBE_PATH")"
  echo "$(stamp) round ${i} probe ${probe}"
  if [ "$probe" = "401" ]; then
    refresh="$(curl -k -s -o /dev/null -w "%{http_code}" -b "$JAR" -c "$JAR" -X POST "${BASE}${REFRESH_PATH}")"
    echo "$(stamp) refresh ${refresh}"
    after="$(call "$PROBE_PATH")"
    echo "$(stamp) probe after refresh ${after}"
    break
  fi
  sleep "$INTERVAL"
done

show_jar
