#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:?usage: run_load.sh single|scaled}"
peak="${PEAK_RPS:-60}"
settle="${SETTLE_SECONDS:-420}"
image="grafana/k6:2.3.0@sha256:e66db15b860113878fa74670e31f5e274830b7b6e42c8bff28b2f2d86a257603"
csv="${repo}/.build/hpa-${mode}.csv"
summary="${repo}/.build/load-${mode}.json"

wait_for_one() {
  for _ in $(seq 1 90); do
    ready="$(kubectl -n theft get deploy backend -o jsonpath='{.status.readyReplicas}')"
    want="$(kubectl -n theft get hpa backend -o jsonpath='{.status.desiredReplicas}')"
    [[ "$ready" == "1" && "$want" == "1" ]] && return 0
    sleep 5
  done
  echo "backend did not settle at 1 replica" >&2
  return 1
}

"${repo}/tools/hpa-proof/load_profile.sh" "$mode"
wait_for_one
echo "settled at 1 replica, starting load peak=${peak} rps"

"${repo}/tools/hpa-proof/watch_hpa.sh" "$csv" &
watcher=$!
trap 'kill "$watcher" 2>/dev/null || true' EXIT

rc=0
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e PEAK_RPS="$peak" -e SSL_CERT_FILE=/certs/ca.crt \
  -v "${repo}/tools/hpa-proof:/scripts:ro" \
  -v "${repo}/config/auth/seed/viewer:/secrets/password:ro" \
  -v "${repo}/config/traefik/certs/ca.crt:/certs/ca.crt:ro" \
  -v "${repo}/.build:/out" \
  "$image" run --quiet --summary-export "/out/load-${mode}.json" /scripts/load.js || rc=$?

echo "k6 exit ${rc}, watching scale-down for ${settle}s"
sleep "$settle"
kill "$watcher" 2>/dev/null || true
echo "timeline ${csv}"
echo "summary ${summary}"
exit "$rc"
