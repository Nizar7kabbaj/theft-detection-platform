#!/usr/bin/env bash
set -euo pipefail

services=(ai api camera detect-gate notification)
failed=()

for service in "${services[@]}"; do
  if ! uv export --frozen --no-emit-project --directory "services/${service}" --format requirements-txt \
      | pip-audit --no-deps -r /dev/stdin; then
    failed+=("${service}")
  fi
done

if ((${#failed[@]} > 0)); then
  printf 'vulnerabilities found in: %s\n' "${failed[*]}" >&2
  exit 1
fi
