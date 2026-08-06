#!/usr/bin/env bash
set -euo pipefail
GRPCIO_TOOLS_VERSION="1.71.2"
usage() {
  cat >&2 <<'EOF'
usage: tools/scripts/gen_proto.sh <target>
  target: backend | ai-service | notification-service | camera-service | detect-gate-service | auth-service | audit-service
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
    auth-service)         echo "services/auth/app/server/grpc_gen" ;;
    audit-service)        echo "services/audit/app/server/grpc_gen" ;;
    *)                    return 1 ;;
  esac
}
resolve_protos() {
  case "$1" in
    backend)              echo "common.proto inference.proto alert.proto auth.proto" ;;
    ai-service)           echo "common.proto inference.proto alert.proto presence.proto" ;;
    notification-service) echo "common.proto alert.proto" ;;
    camera-service)       echo "common.proto inference.proto" ;;
    detect-gate-service)  echo "common.proto presence.proto" ;;
    auth-service)         echo "auth.proto" ;;
    audit-service)        echo "common.proto audit.proto" ;;
    *)                    return 1 ;;
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
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -v "${repo_root}/proto:/proto:ro" \
    -v "${out_host}:/out" \
    -v "${PROTOC_CACHE:-${HOME}/.cache/theft-protoc}:/tmp/.cache" \
    -w /out \
    python:3.12-slim \
    sh -c "pip install --quiet --cache-dir /tmp/.cache/pip grpcio-tools==${GRPCIO_TOOLS_VERSION} \
      && python -m grpc_tools.protoc \
        -I /proto \
        --python_out=/out \
        --grpc_python_out=/out \
        ${proto_args}" || {
    echo "protoc failed for ${target}" >&2
    return 1
  }
  local f
  for f in "${out_host}"/*_pb2.py "${out_host}"/*_pb2_grpc.py; do
    [[ -e "${f}" ]] || continue
    sed -i -E 's/^import ([a-z_][a-z0-9_]*)_pb2 as/from . import \1_pb2 as/' "${f}"
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
    backend|ai-service|notification-service|camera-service|detect-gate-service|auth-service|audit-service)
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
