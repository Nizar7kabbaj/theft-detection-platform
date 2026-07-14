#!/usr/bin/env bash
set -uo pipefail
COMPILER_SERVICE="ai"

usage() {
  cat >&2 <<'EOF'
usage: tools/scripts/gen_proto.sh <target>
  target: backend | ai-service | notification-service | camera-service | detect-gate-service
generates python grpc stubs from proto/ into the matching service grpc_gen path
EOF
}
resolve_outdir() {
  case "$1" in
    backend)              echo "services/api/app/grpc_gen" ;;
    ai-service)           echo "services/ai/app/grpc_gen" ;;
    notification-service) echo "services/notification/app/server/grpc_gen" ;;
    camera-service)       echo "services/camera/app/grpc_gen" ;;
    detect-gate-service)  echo "services/detect-gate/app/grpc_gen" ;;
  esac
}

resolve_protos() {
  case "$1" in
    backend)              echo "common.proto inference.proto alert.proto" ;;
    ai-service)           echo "common.proto inference.proto alert.proto presence.proto" ;;
    notification-service) echo "common.proto alert.proto" ;;
    camera-service)       echo "common.proto inference.proto" ;;
    detect-gate-service)  echo "common.proto presence.proto" ;;
  esac
}

generate() {
  local target="$1"
  local repo_root="$2"
  local outdir protos out_host
  outdir="$(resolve_outdir "${target}")"
  protos="$(resolve_protos "${target}")"
  out_host="${repo_root}/${outdir}"
  mkdir -p "${out_host}" || {
    echo "cannot create ${out_host}" >&2
    return 1
  }

  local proto_args=""
  local p
  for p in ${protos}; do
    proto_args="${proto_args} /proto/${p}"
  done
  docker compose run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    -v "${repo_root}/proto:/proto:ro" \
    -v "${out_host}:/out" \
    -w /app \
    "${COMPILER_SERVICE}" \
    python -m grpc_tools.protoc \
      -I /proto \
      --python_out=/out \
      --grpc_python_out=/out \
      ${proto_args} || {
    echo "protoc failed for ${target}" >&2
    return 1
  }

  local f
  for f in "${out_host}"/*_pb2.py "${out_host}"/*_pb2_grpc.py; do
    [[ -e "${f}" ]] || continue
    sed -i 's/^import \(common\|inference\|alert\|presence\)_pb2 as/from . import \1_pb2 as/' "${f}"
  done
  echo "generated in ${outdir}:"
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
    backend|ai-service|notification-service|camera-service|detect-gate-service)
      ;;
    *)
      echo "unknown target: $1" >&2
      usage
      exit 2
      ;;
  esac
  local repo_root
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || {
    echo "cannot resolve repo root" >&2
    exit 1
  }
  generate "$1" "${repo_root}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
  exit 0
fi
