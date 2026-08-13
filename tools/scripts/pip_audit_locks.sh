#!/usr/bin/env bash
set -euo pipefail

services=(ai api audit auth camera detect-gate notification)
vulnerable=()
unresolved=()

for service in "${services[@]}"; do
  requirements="$(mktemp)"
  trap 'rm -f "${requirements}"' RETURN

  uv export --frozen --no-hashes --no-emit-project --directory "services/${service}" \
    --format requirements-txt \
    | sed -E 's/^([A-Za-z0-9._-]+==[0-9][^+ ]*)\+[A-Za-z0-9.]+/\1/' \
    | grep -vE '^nvidia-[a-z0-9-]+-cu12==' \
    | grep -vE '^cuda-' \
    > "${requirements}"

  printf '\n=== %s\n' "${service}"
  if output="$(pip-audit --no-deps -r "${requirements}" 2>&1)"; then
    printf '%s\n' "${output}"
  elif printf '%s' "${output}" | grep -q 'No matching distribution\|internal pip failure'; then
    printf '%s\n' "${output}" >&2
    unresolved+=("${service}")
  else
    printf '%s\n' "${output}"
    vulnerable+=("${service}")
  fi

  rm -f "${requirements}"
  trap - RETURN
done

status=0

if ((${#unresolved[@]} > 0)); then
  printf 'could not resolve dependencies for: %s\n' "${unresolved[*]}" >&2
  status=1
fi

if ((${#vulnerable[@]} > 0)); then
  printf 'vulnerabilities found in: %s\n' "${vulnerable[*]}" >&2
  status=1
fi

exit "${status}"
