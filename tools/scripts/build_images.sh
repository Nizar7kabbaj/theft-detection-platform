#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly REGISTRY="${REGISTRY:-localhost:5001}"
readonly BUILD_DIR="${REPO_ROOT}/.build"
readonly DIGEST_DIR="${BUILD_DIR}/digests"
readonly VALUES_FILE="${BUILD_DIR}/image-values.yaml"
readonly CORE=(backend web auth audit notification notification-worker)
readonly GPU=(ai-models ai camera detect-gate)

declare -A CONTEXT=(
  [backend]=services/api [web]=apps/web [auth]=services/auth [audit]=services/audit
  [notification]=services/notification [notification-worker]=services/notification
  [ai]=services/ai [camera]=services/camera [detect-gate]=services/detect-gate
  [ai-models]=ml
)
declare -A TARGET=(
  [backend]=runtime [web]=runtime [auth]=runtime [audit]=runtime
  [notification]=server [notification-worker]=worker
  [ai]=runtime [camera]=runtime [detect-gate]=runtime
  [ai-models]=models
)
declare -A REPOSITORY=(
  [backend]=theft-backend [web]=theft-web [auth]=theft-auth [audit]=theft-audit
  [notification]=theft-notification-server [notification-worker]=theft-notification-worker
  [ai]=theft-ai [camera]=theft-camera [detect-gate]=theft-detect-gate
  [ai-models]=theft-ai-models
)

usage() {
  cat <<EOF
usage: $(basename "$0") [component...|all]

builds images with an explicit target, pushes them to ${REGISTRY} and records
the registry digests in ${VALUES_FILE#"${REPO_ROOT}/"}.
default: ${CORE[*]}
all:     ${CORE[*]} ${GPU[*]}
EOF
}

log() { printf '%s\n' "$*" >&2; }
die() { log "error: $*"; exit 1; }

require() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing command: ${cmd}"
  done
}

image_tag() {
  local sha
  sha="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    sha="${sha}-dirty"
  fi
  printf '%s' "$sha"
}

build_one() {
  local name="$1" tag="$2" meta digest
  [[ -n "${CONTEXT[$name]:-}" ]] || die "unknown component: ${name}"
  meta="$(mktemp)"
  local args=(
    --platform linux/amd64
    --target "${TARGET[$name]}"
    --tag "${REGISTRY}/${REPOSITORY[$name]}:${tag}"
    --provenance=mode=max
    --sbom=true
    --metadata-file "$meta"
    --push
  )
  log "building ${name} (${TARGET[$name]})"
  docker buildx build "${args[@]}" "${REPO_ROOT}/${CONTEXT[$name]}"
  digest="$(jq -r '."containerimage.digest" // empty' "$meta")"
  rm -f "$meta"
  [[ "$digest" == sha256:* ]] || die "no registry digest for ${name}"
  printf '%s %s %s\n' "${REPOSITORY[$name]}" "$tag" "$digest" > "${DIGEST_DIR}/${name}"
  log "${name} -> ${digest}"
}

write_values() {
  local file name repo tag digest
  {
    printf 'global:\n  image:\n    registry: %s\ncomponents:\n' "$REGISTRY"
    for file in "$DIGEST_DIR"/*; do
      [[ -f "$file" ]] || continue
      name="$(basename "$file")"
      [[ "$name" == "ai-models" ]] && continue
      read -r repo tag digest < "$file"
      printf '  %s:\n    image:\n      repository: %s\n      tag: "%s"\n      digest: %s\n' "$name" "$repo" "$tag" "$digest"
      if [[ "$name" == "notification-worker" ]]; then
        printf '  notification-beat:\n    image:\n      repository: %s\n      tag: "%s"\n      digest: %s\n' "$repo" "$tag" "$digest"
      fi
    done
    if [[ -f "${DIGEST_DIR}/ai-models" ]]; then
      read -r repo tag digest < "${DIGEST_DIR}/ai-models"
      printf 'modelImage:\n  repository: %s\n  tag: "%s"\n  digest: %s\n' "$repo" "$tag" "$digest"
    fi
  } > "$VALUES_FILE"
  log "wrote ${VALUES_FILE#"${REPO_ROOT}/"}"
}

main() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
  require docker git jq
  local components=("$@") tag name
  if [[ ${#components[@]} -eq 0 ]]; then
    components=("${CORE[@]}")
  elif [[ "${components[0]}" == "all" ]]; then
    components=("${CORE[@]}" "${GPU[@]}")
  fi
  mkdir -p "$DIGEST_DIR"
  tag="$(image_tag)"
  for name in "${components[@]}"; do
    build_one "$name" "$tag"
  done
  write_values
}

main "$@"
