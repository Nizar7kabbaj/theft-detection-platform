#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/theft-detection-platform}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXCLUDES_FILE="${EXCLUDES_FILE:-$SCRIPT_DIR/excludes.txt}"
PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.restic-password}"

USB_REPO="${USB_REPO:-/mnt/restic-usb}"
AZURE_ACCOUNT="${AZURE_ACCOUNT:-stbackuptheft}"
AZURE_CONTAINER="${AZURE_CONTAINER:-backups}"

HOST_TAG="$(hostname)"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [usb|azure|both]
  usb    — back up to the local USB repo only
  azure  — back up to the Azure Blob repo only
  both   — back up to both (default)

Environment overrides:
  PROJECT_ROOT      source directory (default: \$HOME/theft-detection-platform)
  USB_REPO          USB repo mount point (default: /mnt/restic-usb)
  AZURE_ACCOUNT     storage account name (default: stbackuptheft)
  AZURE_CONTAINER   blob container name (default: backups)
  RESTIC_PASSWORD_FILE  password file path (default: \$HOME/.restic-password)
EOF
}

target="${1:-both}"
case "$target" in
  usb|azure|both) ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac

command -v restic >/dev/null 2>&1 || fail "restic not on PATH"
[[ -f "$PASSWORD_FILE" ]]         || fail "password file missing: $PASSWORD_FILE"
[[ -f "$EXCLUDES_FILE" ]]         || fail "excludes file missing: $EXCLUDES_FILE"
[[ -d "$PROJECT_ROOT" ]]          || fail "project root missing: $PROJECT_ROOT"

export RESTIC_PASSWORD_FILE="$PASSWORD_FILE"

backup_usb() {
  [[ -d "$USB_REPO" ]] || fail "USB repo path not present: $USB_REPO"

  export RESTIC_REPOSITORY="$USB_REPO"
  unset AZURE_ACCOUNT_NAME AZURE_ACCOUNT_KEY AZURE_ACCOUNT_SAS

  if ! restic snapshots >/dev/null 2>&1; then
    log "USB repo not initialized at $USB_REPO — running restic init"
    restic init
  fi

  log "Backing up $PROJECT_ROOT to USB repo $USB_REPO"
  restic backup "$PROJECT_ROOT" \
    --exclude-file="$EXCLUDES_FILE" \
    --tag "host=$HOST_TAG" \
    --tag "ts=$TIMESTAMP" \
    --tag "target=usb"
  log "USB backup complete"
}

backup_azure() {
  command -v az >/dev/null 2>&1 || fail "az CLI not on PATH"
  az account show >/dev/null 2>&1 || fail "not logged in to Azure. Run: az login"

  export AZURE_ACCOUNT_NAME="$AZURE_ACCOUNT"
  unset AZURE_ACCOUNT_KEY AZURE_ACCOUNT_SAS
  export RESTIC_REPOSITORY="azure:${AZURE_CONTAINER}:/"

  if ! restic snapshots >/dev/null 2>&1; then
    log "Azure repo not initialized — running restic init"
    restic init
  fi

  log "Backing up $PROJECT_ROOT to Azure repo $RESTIC_REPOSITORY"
  restic backup "$PROJECT_ROOT" \
    --exclude-file="$EXCLUDES_FILE" \
    --tag "host=$HOST_TAG" \
    --tag "ts=$TIMESTAMP" \
    --tag "target=azure"
  log "Azure backup complete"
}

[[ "$target" == "usb"   || "$target" == "both" ]] && backup_usb
[[ "$target" == "azure" || "$target" == "both" ]] && backup_azure

log "All requested backups finished."