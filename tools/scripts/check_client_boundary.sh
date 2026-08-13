#!/usr/bin/env bash
set -euo pipefail

web_root="apps/web"
violations=()

while IFS= read -r file; do
  if head -3 "${file}" | grep -q '^"use client"'; then
    violations+=("${file}")
  fi
done < <(find "${web_root}/app" -type f \( -name 'layout.tsx' -o -name 'page.tsx' \) 2>/dev/null)

while IFS= read -r file; do
  if grep -q 'from "@/lib/dal/' "${file}" && head -3 "${file}" | grep -q '^"use client"'; then
    violations+=("${file}")
  fi
done < <(find "${web_root}" -type f -name '*.tsx' -not -path '*/node_modules/*' -not -path '*/.next/*' 2>/dev/null)

if ((${#violations[@]} > 0)); then
  printf 'client directive not allowed in routing entry points or alongside server data access:\n' >&2
  printf '  %s\n' "${violations[@]}" >&2
  exit 1
fi

exit 0
