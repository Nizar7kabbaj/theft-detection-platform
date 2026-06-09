#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p backend/app/grpc_gen

docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/proto:/proto:ro" \
  -w /app \
  backend \
  python -m grpc_tools.protoc \
    -I /proto \
    --python_out=app/grpc_gen \
    --grpc_python_out=app/grpc_gen \
    /proto/common.proto /proto/inference.proto /proto/alert.proto

for f in backend/app/grpc_gen/*_pb2.py backend/app/grpc_gen/*_pb2_grpc.py; do
  sed -i 's/^import \(common\|inference\|alert\)_pb2 as/from . import \1_pb2 as/' "$f"
done

echo "generated:"
ls -1 backend/app/grpc_gen/
