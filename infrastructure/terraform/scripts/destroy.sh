#!/usr/bin/env bash


set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/tf.sh" "${1:?usage: destroy.sh <env>}" destroy "${@:2}"