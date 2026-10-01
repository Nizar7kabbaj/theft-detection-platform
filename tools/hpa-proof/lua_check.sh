#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image="$(grep -m1 -oE 'docker.io/library/redis@sha256:[0-9a-f]{64}' "$repo/deploy/helm/theft-data/values.yaml")"
name=lua-check
port=6390

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --rm --name "$name" -p "127.0.0.1:${port}:6379" "$image" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$name" redis-cli ping >/dev/null 2>&1 && break
  sleep 0.5
done
docker exec "$name" redis-server --version

cd "$repo/services/api"
uv run --frozen python "$repo/tools/hpa-proof/lua_check.py" "$port"
