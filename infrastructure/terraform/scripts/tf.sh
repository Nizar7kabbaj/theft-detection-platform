#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TF_ROOT/../.." && pwd)"

ENVS_DIR="$TF_ROOT/environments"

info() { printf '[info] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*" >&2; }
err()  { printf '[err]  %s\n' "$*" >&2; }
ok()   { printf '[ok]   %s\n' "$*"; }

usage() {
  cat <<EOF
tf.sh — terraform wrapper

usage:
  $(basename "$0") <env> <action> [terraform-args...]

environments:  one of the directories under infrastructure/terraform/environments/
actions:       init | fmt | validate | plan | apply | destroy | output | console

examples:
  $(basename "$0") dev init
  $(basename "$0") dev plan
  $(basename "$0") dev apply
  $(basename "$0") dev destroy

notes:
  apply requires a fresh plan file (tfplan). run plan first.
  destroy runs a destroy plan first and asks you to type the env name.
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

ENV_NAME="$1"; shift
ACTION="$1";   shift
EXTRA_ARGS=("$@")

ENV_DIR="$ENVS_DIR/$ENV_NAME"
PLAN_FILE="tfplan"
DESTROY_PLAN_FILE="tfplan.destroy"

if [[ ! -d "$ENV_DIR" ]]; then
  err "environment '$ENV_NAME' not found at $ENV_DIR"
  echo "available environments:" >&2
  for d in "$ENVS_DIR"/*/; do
    [[ -d "$d" ]] && echo "  $(basename "$d")" >&2
  done
  exit 1
fi

TF_ENV_FILE="$REPO_ROOT/.tf-env"
if [[ -f "$TF_ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$TF_ENV_FILE"
  set +a
else
  warn ".tf-env not found at repo root. copy .tf-env.example and fill it in."
fi

require_azure() {
  if ! command -v az >/dev/null 2>&1; then
    err "azure cli not installed. install it and run 'az login'."
    exit 1
  fi
  if ! az account show >/dev/null 2>&1; then
    err "not logged in to azure. run: az login"
    exit 1
  fi
  if [[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
    local current
    current="$(az account show --query id -o tsv)"
    if [[ "$current" != "$AZURE_SUBSCRIPTION_ID" ]]; then
      err "wrong subscription."
      echo "  expected: $AZURE_SUBSCRIPTION_ID" >&2
      echo "  current:  $current" >&2
      echo "  fix:      az account set --subscription $AZURE_SUBSCRIPTION_ID" >&2
      exit 1
    fi
    ok "subscription $current"
  else
    warn "AZURE_SUBSCRIPTION_ID not set in .tf-env, skipping subscription guard."
  fi
}

cd "$ENV_DIR"
info "env: $ENV_NAME"
info "dir: $ENV_DIR"

case "$ACTION" in
  init)
    require_azure
    terraform init "${EXTRA_ARGS[@]}"
    ;;

  fmt)
    terraform fmt -recursive "${EXTRA_ARGS[@]}"
    ;;

  validate)
    terraform validate "${EXTRA_ARGS[@]}"
    ;;

  plan)
    require_azure
    info "writing plan to $PLAN_FILE"
    terraform plan -out="$PLAN_FILE" "${EXTRA_ARGS[@]}"
    ok "plan saved. review above, then: $(basename "$0") $ENV_NAME apply"
    ;;

  apply)
    require_azure
    if [[ ! -f "$PLAN_FILE" ]]; then
      err "no plan file ($PLAN_FILE). run plan first:"
      echo "  $(basename "$0") $ENV_NAME plan" >&2
      exit 1
    fi
    if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
      err "apply does not accept extra args when a plan file is in use."
      echo "  extra args received: ${EXTRA_ARGS[*]}" >&2
      echo "  reason: flags like -target would silently override the plan." >&2
      exit 1
    fi
    if [[ -n "$(find "$PLAN_FILE" -mmin +30 2>/dev/null)" ]]; then
      warn "plan file is older than 30 minutes."
      read -r -p "apply anyway? [y/N] " confirm
      [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { info "aborted."; exit 1; }
    fi
    terraform apply "$PLAN_FILE"
    rm -f "$PLAN_FILE"
    ok "applied. plan file removed."
    ;;

  destroy)
    require_azure
    info "writing destroy plan to $DESTROY_PLAN_FILE"
    terraform plan -destroy -out="$DESTROY_PLAN_FILE" "${EXTRA_ARGS[@]}"
    warn "review the destroy plan above. all listed resources will be deleted."
    echo "  dir: $ENV_DIR" >&2
    read -r -p "type the env name to confirm: " confirm
    if [[ "$confirm" != "$ENV_NAME" ]]; then
      err "confirmation failed. aborted."
      rm -f "$DESTROY_PLAN_FILE"
      exit 1
    fi
    terraform apply "$DESTROY_PLAN_FILE"
    rm -f "$DESTROY_PLAN_FILE"
    ok "destroyed. plan file removed."
    ;;

  output)
    terraform output "${EXTRA_ARGS[@]}"
    ;;

  console)
    terraform console "${EXTRA_ARGS[@]}"
    ;;

  *)
    err "unknown action: $ACTION"
    usage
    exit 1
    ;;
esac
