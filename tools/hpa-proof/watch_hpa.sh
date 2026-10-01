#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

out="${1:?usage: watch_hpa.sh <csv>}"
echo "ts,current,desired,cpu_percent,ready" >"$out"
while true; do
  line="$(kubectl -n theft get hpa backend \
    -o jsonpath='{.status.currentReplicas},{.status.desiredReplicas},{.status.currentMetrics[0].resource.current.averageUtilization}' \
    2>/dev/null)" || line=",,"
  ready="$(kubectl -n theft get deploy backend -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" || ready=""
  echo "$(date +%s),${line},${ready:-0}" >>"$out"
  sleep 5
done
