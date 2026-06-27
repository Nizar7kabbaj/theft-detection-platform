#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: scripts/gen_proto.sh <target>
  target: backend | ai-service | alert-service
generates python grpc stubs from proto/ into <target>/app/grpc_gen
EOF
}

generate() {
  local target="$1"
  local out_host="${PWD}/${target}/app/grpc_gen"

  mkdir -p "${out_host}"

  docker compose run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    -v "${PWD}/proto:/proto:ro" \
    -v "${out_host}:/out" \
    -w /app \
    backend \
    python -m grpc_tools.protoc \
      -I /proto \
      --python_out=/out \
      --grpc_python_out=/out \
      /proto/common.proto /proto/inference.proto /proto/alert.proto

  local f
  for f in "${out_host}"/*_pb2.py "${out_host}"/*_pb2_grpc.py; do
    sed -i 's/^import \(common\|inference\|alert\)_pb2 as/from . import \1_pb2 as/' "$f"
  done

  echo "generated in ${target}/app/grpc_gen:"
  ls -1 "${out_host}"
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    exit 2
  fi

  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    backend|ai-service|alert-service)
      ;;
    *)
      echo "unknown target: $1" >&2
      usage
      exit 2
      ;;
  esac

  cd "$(dirname "$0")/.."
  generate "$1"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
