#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TF_ROOT/../.." && pwd)"

ENVS_DIR="$TF_ROOT/environments"

if [[ -t 1 ]]; then
  RED=$'\033[0;31m';   GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
  BLUE=$'\033[0;34m';  BOLD=$'\033[1m';     RESET=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

info() { printf '%s[info]%s  %s\n' "$BLUE"   "$RESET" "$*"; }
warn() { printf '%s[warn]%s  %s\n' "$YELLOW" "$RESET" "$*" >&2; }
err()  { printf '%s[err]%s   %s\n' "$RED"    "$RESET" "$*" >&2; }
ok()   { printf '%s[ok]%s    %s\n' "$GREEN"  "$RESET" "$*"; }

usage() {
  cat <<EOF
${BOLD}tf.sh${RESET} — Terraform wrapper

Usage:
  $(basename "$0") <env> <action> [terraform-args...]

Environments:  one of the directories under infrastructure/terraform/environments/
Actions:       init | fmt | validate | plan | apply | destroy | output | console

Examples:
  $(basename "$0") dev init
  $(basename "$0") dev plan
  $(basename "$0") dev apply
  $(basename "$0") dev destroy

Notes:
  apply requires a fresh plan file (tfplan). Run plan first.
  destroy asks you to type the env name to confirm.
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

if [[ ! -d "$ENV_DIR" ]]; then
  err "environment '$ENV_NAME' not found at $ENV_DIR"
  echo "available environments:" >&2
  ls -1 "$ENVS_DIR" 2>/dev/null | sed 's/^/  /' >&2 || true
  exit 1
fi

TF_ENV_FILE="$REPO_ROOT/.tf-env"
if [[ -f "$TF_ENV_FILE" ]]; then
  set -a
  . "$TF_ENV_FILE"
  set +a
else
  warn ".tf-env not found at repo root. Copy .tf-env.example and fill it in."
fi

require_azure() {
  if ! command -v az >/dev/null 2>&1; then
    err "Azure CLI not installed. Install it and run 'az login'."
    exit 1
  fi
  if ! az account show >/dev/null 2>&1; then
    err "not logged in to Azure. Run: az login"
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

# action dispatch
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
      err "no plan file ($PLAN_FILE). Run plan first:"
      echo "  $(basename "$0") $ENV_NAME plan" >&2
      exit 1
    fi
    if [[ -n "$(find "$PLAN_FILE" -mmin +30 2>/dev/null)" ]]; then
      warn "plan file is older than 30 minutes."
      read -r -p "apply anyway? [y/N] " confirm
      [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { info "aborted."; exit 1; }
    fi
    terraform apply "${EXTRA_ARGS[@]}" "$PLAN_FILE"
    rm -f "$PLAN_FILE"
    ok "applied. plan file removed."
    ;;

  destroy)
    require_azure
    warn "about to DESTROY all resources in env '$ENV_NAME'."
    echo "  dir: $ENV_DIR" >&2
    read -r -p "type the env name to confirm: " confirm
    if [[ "$confirm" != "$ENV_NAME" ]]; then
      err "confirmation failed. aborted."
      exit 1
    fi
    terraform destroy "${EXTRA_ARGS[@]}"
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
