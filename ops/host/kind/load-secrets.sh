#!/usr/bin/env bash
set -Eeuo pipefail

readonly KCTX="${KCTX:-kind-theft-dev}"
readonly NAMESPACE="theft"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REPO_ROOT
readonly CONFIG_DIR="${REPO_ROOT}/config"
readonly MANAGER="load-secrets"
readonly PART_OF="app.kubernetes.io/part-of=theft-detection-platform"

usage() {
  cat <<EOF
usage: $(basename "$0")

creates or updates every secret the ${NAMESPACE} namespace needs from the files under config/.
values are read from disk and sent to the api server only, never printed.
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

need_file() {
  [[ -s "$1" ]] || die "missing or empty: ${1#"${REPO_ROOT}/"}"
}

apply_manifest() {
  kubectl --context "$KCTX" label --local -f - "$PART_OF" "$@" -o yaml \
    | kubectl --context "$KCTX" apply --server-side --field-manager="$MANAGER" -f - >/dev/null
}

apply_secret() {
  local name="$1"
  shift
  local args=() spec path
  for spec in "$@"; do
    path="${CONFIG_DIR}/${spec#*=}"
    need_file "$path"
    args+=("--from-file=${spec%%=*}=${path}")
  done
  kubectl --context "$KCTX" -n "$NAMESPACE" create secret generic "$name" "${args[@]}" \
    --dry-run=client -o yaml | apply_manifest
  log "${name}: $# keys"
}

apply_role_secret() {
  local role="$1" file="${CONFIG_DIR}/$2"
  local name="pg-role-${role//_/-}"
  need_file "$file"
  kubectl --context "$KCTX" -n "$NAMESPACE" create secret generic "$name" \
    --type kubernetes.io/basic-auth \
    --from-literal=username="$role" \
    --from-file=password=<(tr -d '\r\n' < "$file") \
    --dry-run=client -o yaml | apply_manifest cnpg.io/reload=true
  log "${name}: role ${role}"
}

apply_configmap() {
  local name="$1"
  shift
  local args=() spec path
  for spec in "$@"; do
    path="${CONFIG_DIR}/${spec#*=}"
    need_file "$path"
    args+=("--from-file=${spec%%=*}=${path}")
  done
  kubectl --context "$KCTX" -n "$NAMESPACE" create configmap "$name" "${args[@]}" \
    --dry-run=client -o yaml | apply_manifest
  log "${name}: $# keys"
}

apply_env_secret() {
  local name="$1" key="$2" file="${REPO_ROOT}/$3" var="$4"
  need_file "$file"
  grep -q "^${var}=." "$file" || die "${var} is not set in $3"
  kubectl --context "$KCTX" -n "$NAMESPACE" create secret generic "$name" \
    --from-file="${key}"=<(sed -n "s/^${var}=//p" "$file" | tr -d '\r\n') \
    --dry-run=client -o yaml | apply_manifest
  log "${name}: ${key}"
}

apply_seed_secret() {
  local name="$1" dir="${CONFIG_DIR}/$2"
  shift 2
  local rel="${dir#"${REPO_ROOT}/"}"
  local args=() entries=() entry path rel_path user mode
  local -A seen=()
  [[ -d "$dir" ]] || die "missing directory: ${rel}"
  shopt -s nullglob
  for path in "$dir"/*; do
    entries+=("${path##*/}=${path}")
  done
  shopt -u nullglob
  for entry in "$@"; do
    [[ "$entry" == ?*=?* ]] || die "invalid seed mapping: ${entry}"
    entries+=("${entry%%=*}=${CONFIG_DIR}/${entry#*=}")
  done
  (( ${#entries[@]} > 0 )) || die "no seed users in ${rel}"
  for entry in "${entries[@]}"; do
    user="${entry%%=*}"
    path="${entry#*=}"
    rel_path="${path#"${REPO_ROOT}/"}"
    [[ "$user" =~ ^[a-z0-9][a-z0-9._-]{2,49}$ ]] || die "invalid username: ${user}"
    [[ -z "${seen[$user]:-}" ]] || die "seed user defined twice: ${user}"
    seen[$user]=1
    [[ -f "$path" && ! -L "$path" ]] || die "not a regular file: ${rel_path}"
    need_file "$path"
    mode="$(stat -c '%a' "$path")"
    [[ "$mode" == "600" ]] || die "${rel_path} must be mode 600, found ${mode}"
    args+=("--from-file=${user}=${path}")
  done
  kubectl --context "$KCTX" -n "$NAMESPACE" create secret generic "$name" "${args[@]}" \
    --dry-run=client -o yaml | apply_manifest
  log "${name}: ${#entries[@]} users"
}

main() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
  require kubectl tr stat
  kubectl --context "$KCTX" get namespace "$NAMESPACE" >/dev/null 2>&1 || die "namespace ${NAMESPACE} not found"

  apply_secret backend-secrets \
    mongo_password=mongodb/secrets/mongo_api_password \
    api_redis_password=redis/api_redis_password \
    stream_reader_redis_password=redis/stream_reader_redis_password

  apply_secret auth-secrets \
    postgres_password=postgres/auth_app_postgres_password \
    jwt_private_key=auth/jwt_private.pem \
    jwt_public_key=auth/jwt_public.pem \
    auth_redis_password=redis/auth_redis_password \
    auth_pseudonym_key=audit/pseudonym_key

  apply_secret audit-secrets \
    audit_app_postgres_password=postgres/audit_app_postgres_password \
    audit_redis_password=redis/audit_redis_password \
    audit_pseudonym_key=audit/pseudonym_key \
    audit_checkpoint_private_key=audit/checkpoint_private.pem \
    audit_checkpoint_public_key=audit/checkpoint_public.pem

  apply_secret notification-secrets \
    mongo_password=mongodb/secrets/mongo_notification_password \
    broker_redis_password=redis/broker_redis_password \
    notify_redis_password=redis/notify_redis_password \
    webhook_token=alertmanager/webhook_token

  apply_secret notification-worker-secrets \
    mongo_password=mongodb/secrets/mongo_notification_password \
    broker_redis_password=redis/broker_redis_password \
    notify_redis_password=redis/notify_redis_password \
    telegram_bot_token=telegram/bot_token \
    telegram_callback_key=telegram/callback_key

  apply_secret notification-telegram-secrets \
    mongo_password=mongodb/secrets/mongo_notification_password \
    broker_redis_password=redis/broker_redis_password \
    notify_redis_password=redis/notify_redis_password \
    telegram_bot_token=telegram/bot_token \
    telegram_callback_key=telegram/callback_key

  apply_secret notification-beat-secrets \
    mongo_password=mongodb/secrets/mongo_notification_password \
    broker_redis_password=redis/broker_redis_password \
    notify_redis_password=redis/notify_redis_password

  apply_secret ai-secrets \
    ai_redis_password=redis/ai_redis_password \
    alert_password=auth/detector_password \
    webhook_token=alertmanager/webhook_token

  apply_secret camera-secrets camera_redis_password=redis/camera_redis_password
  apply_secret detect-gate-secrets gate_redis_password=redis/gate_redis_password

  apply_secret auth-migrate-secrets auth_owner_postgres_password=postgres/auth_owner_postgres_password
  apply_secret audit-migrate-secrets audit_owner_postgres_password=postgres/audit_owner_postgres_password
  apply_secret audit-operator-secrets \
    audit_owner_postgres_password=postgres/audit_owner_postgres_password \
    audit_app_postgres_password=postgres/audit_app_postgres_password \
    audit_pseudonym_key=audit/pseudonym_key \
    audit_checkpoint_public_key=audit/checkpoint_public.pem

  apply_secret mongo-secrets \
    mongo_root_password=mongodb/secrets/mongo_root_password \
    mongo_api_password=mongodb/secrets/mongo_api_password \
    mongo_notification_password=mongodb/secrets/mongo_notification_password \
    mongo_monitor_password=mongodb/secrets/mongo_monitor_password

  apply_secret redis-config redis.conf=redis/redis.conf redis.acl=redis/redis.acl
  apply_secret redis-broker-config redis-broker.conf=redis/redis-broker.conf redis-broker.acl=redis/redis-broker.acl
  apply_secret redis-stream-config redis-stream.conf=redis/redis-stream.conf redis-stream.acl=redis/redis-stream.acl

  apply_role_secret auth_owner postgres/auth_owner_postgres_password
  apply_role_secret auth_app postgres/auth_app_postgres_password
  apply_role_secret audit_owner postgres/audit_owner_postgres_password
  apply_role_secret audit_app postgres/audit_app_postgres_password
  apply_configmap mongo-config mongod.conf=mongodb/mongod.conf
  apply_configmap mongo-init 001-create-service-users.sh=mongodb/init/001-create-service-users.sh
  apply_seed_secret auth-seed-secrets auth/seed detector-ai=auth/detector_password
  apply_env_secret notification-env telegram_chat_id services/notification/.env TELEGRAM_CHAT_ID
  apply_env_secret auth-env telegram_bot_username services/auth/.env AUTH_TELEGRAM_BOT_USERNAME
  log "secrets applied to ${NAMESPACE}"
}

main "$@"
