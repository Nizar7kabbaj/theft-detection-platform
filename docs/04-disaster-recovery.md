# Disaster Recovery

This doc covers the backup-and-restore strategy for the theft-detection-platform laptop: what the backup script captures, what it deliberately skips, the recovery targets, the one-time setup of the two repositories, and the restore procedure step by step.

The backup script lives at `infrastructure/backup/backup.sh`. The exclude patterns live next to it in `infrastructure/backup/excludes.txt`.

## What's backed up

The source is the project working tree at `~/theft-detection-platform/`. The script ships a snapshot of everything in that directory, minus the patterns in `excludes.txt`.

The point of the backup is to recover anything that GitHub cannot:

- `backend/.env` — gitignored, contains MongoDB Atlas credentials, Telegram bot token, Azure subscription ID, signing keys
- `.tf-env` — gitignored, holds `AZURE_SUBSCRIPTION_ID` for the terraform helper scripts
- `environments/*/terraform.tfvars` — gitignored, contains real values for each environment
- Any local-only config that drifts from the `.example` files committed to git

A full working-tree snapshot is more useful than a gitignored-only snapshot at restore time. After a restore, you have a recognizable working directory in one step, instead of `git clone` plus selective file recovery.

## What's not backed up

The `excludes.txt` patterns skip everything that's large, regenerable, or both:

| Pattern | Why excluded |
|---|---|
| `venv/` | Regenerable via `pip install -r ai-model/requirements.txt` |
| `node_modules/` | Regenerable via `npm install` |
| `ai-model/data/` | Dataset re-downloadable from Kaggle / source repo |
| `ai-model/models/*.pt` | Model weights live in git for now (small), recoverable from GitHub |
| `ai-model/outputs/` | Runtime snapshots, alerts, evaluation outputs — all regenerable |
| `.terraform/` | Provider downloads, regenerable via `terraform init` |
| `*.tfstate` | State lives in Azure Blob, not on local disk |
| `__pycache__/`, `*.pyc`, `.pytest_cache/` | Build artifacts |
| `.DS_Store`, `Thumbs.db` | OS metadata |

If a future ticket adds anything large and regenerable, it gets a new exclude line at the same time.

## RPO and RTO

| Target | Value |
|---|---|
| RPO (recovery point objective) | 24 hours |
| RTO (recovery time objective) | 90 minutes |

The 24-hour RPO assumes the script runs once per day. A scheduled trigger is a separate future ticket. For now backups are manual, and the practical RPO is "whenever I last ran the script."

The 90-minute RTO splits into two phases. Restic restore lands the working tree on disk in 10 minutes or so. Rebuilding the venv, pulling Docker images, and running `docker compose up` follows `docs/01-linux-setup.md` and takes the rest of the budget. The drill in this same epic measures the actual numbers and updates this target if reality disagrees.

## Repositories

Two repositories, parallel and independent:

| Repository | Path | Purpose |
|---|---|---|
| USB | `/mnt/restic-usb` | Fast local recovery |
| Azure Blob | `azure:backups:/` on `stbackuptheft` | Off-site, survives laptop loss |

Restic encrypts both repositories with the same password. The Azure container shares the lifecycle of the state backend (`sttfstatetheft`) — provisioned once manually, never destroyed.

### One-time USB repo setup

1. Plug in the external USB drive
2. Format it ext4 if it isn't already
3. Mount it at `/mnt/restic-usb` (add an entry to `/etc/fstab` for persistence)
4. The script runs `restic init` automatically on first use

### One-time Azure repo setup

The storage account, container, and RBAC role assignment are a one-time manual provision. The script does not create them:

```bash
az group create \
  --name rg-backup-theft \
  --location spaincentral

az storage account create \
  --name stbackuptheft \
  --resource-group rg-backup-theft \
  --location spaincentral \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false

az storage container create \
  --name backups \
  --account-name stbackuptheft \
  --auth-mode login

# Grant the signed-in user data-plane access
USER_OID=$(az ad signed-in-user show --query id -o tsv)
SCOPE=$(az storage account show -n stbackuptheft -g rg-backup-theft --query id -o tsv)
az role assignment create \
  --assignee "$USER_OID" \
  --role "Storage Blob Data Contributor" \
  --scope "$SCOPE"
```

The script reaches the storage account via Azure AD — there is no storage key in any file or env var. Matches the rest of the project's auth posture.

## Restic password

Generate a strong password and save it twice:

```bash
openssl rand -base64 32 > ~/.restic-password
chmod 600 ~/.restic-password
```

Then copy the same value into a password manager (Bitwarden, 1Password, KeePassXC). If the laptop dies and the file is gone, the password manager copy is the only way the encrypted snapshots become recoverable. Losing both ends of the password means losing the backups, even when the bytes are intact.

## Running a backup manually

```bash
cd ~/theft-detection-platform
./infrastructure/backup/backup.sh both     # default — backs up to both repos
./infrastructure/backup/backup.sh usb      # USB only
./infrastructure/backup/backup.sh azure    # Azure only
```

The script exits non-zero on any prereq failure (missing password file, USB not mounted, no Azure login, etc.). Watch the output for the per-target completion log lines.

Inspect snapshots afterwards:

```bash
# USB
RESTIC_REPOSITORY=/mnt/restic-usb RESTIC_PASSWORD_FILE=~/.restic-password \
  restic snapshots

# Azure
AZURE_ACCOUNT_NAME=stbackuptheft \
RESTIC_REPOSITORY=azure:backups:/ RESTIC_PASSWORD_FILE=~/.restic-password \
  restic snapshots
```

## Cron stub (not installed)

A scheduled trigger is out of scope for this ticket. Once it lands, the entry will look something like:

```cron
# Daily backup at 03:00 (NOT INSTALLED. Separate future ticket handles
# service principal auth, log path, and root-vs-user execution context.)
0 3 * * * /home/nizar/theft-detection-platform/infrastructure/backup/backup.sh both >> ~/.local/state/restic-backup.log 2>&1
```

The future ticket also has to solve unattended Azure auth. `az login` sessions expire after 90 days; a scheduled job needs a service principal or managed identity. Don't enable cron until that's resolved, or backups will silently start failing on day 91.

## Restore procedure

A full restore has three phases. Time the run from start to finish. That's the measured RTO.

### Phase 1 — Restore files

Pick whichever repository the situation favors. USB is faster; Azure is the answer if the USB drive is gone too.

```bash
# USB
export RESTIC_REPOSITORY=/mnt/restic-usb
export RESTIC_PASSWORD_FILE=~/.restic-password

# Or Azure
# az login
# export AZURE_ACCOUNT_NAME=stbackuptheft
# export RESTIC_REPOSITORY=azure:backups:/
# export RESTIC_PASSWORD_FILE=~/.restic-password

# Identify the snapshot to restore
restic snapshots

# Restore to a scratch directory first — never overwrite the live tree blind
mkdir -p ~/restore
restic restore latest --target ~/restore

# The restored tree appears at ~/restore/home/<user>/theft-detection-platform/
ls ~/restore
```

### Phase 2 — Promote to live (or recover specific files)

For a full recovery, move the restored directory into place:

```bash
mv ~/theft-detection-platform ~/theft-detection-platform.old  # safety
mv ~/restore/home/$USER/theft-detection-platform ~/
```

For a partial recovery (single file), copy what you need out of `~/restore` and leave the rest:

```bash
cp ~/restore/home/$USER/theft-detection-platform/backend/.env \
   ~/theft-detection-platform/backend/.env
```

### Phase 3 — Rebuild the runtime

The working tree is back, but venv, Docker images, and node_modules are not (those are in `excludes.txt`). Walk through `docs/01-linux-setup.md`:

1. `pyenv local 3.11.9` and `python -m venv venv` if the venv is missing
2. `pip install -r ai-model/requirements.txt` (CUDA torch wheel first)
3. `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.linux.yml pull`
4. `dctd up -d` and verify `/health` returns healthy

If the terraform stack needs to come back too, `terraform init` from each environment root re-downloads providers and reconnects to the remote state. No state recovery needed — state lives in Azure independently.

## Verifying a backup without restoring

`restic check` walks the repository structure and verifies snapshot integrity:

```bash
RESTIC_REPOSITORY=/mnt/restic-usb RESTIC_PASSWORD_FILE=~/.restic-password \
  restic check
```

Slow on large repos, but the only way to catch silent corruption before a real restore needs the data. Worth running once a month or after any unusual event (disk error, sudden shutdown during backup).

## Other docs in this folder

- `docs/01-linux-setup.md` — local dev environment, prerequisite for the rebuild phase
- `docs/02-iac-foundation.md` — terraform structure, including the state backend that's independent of this backup
- `docs/03-pre-commit.md` — terraform hook install and suppression rationale

## Drill log

### Drill — 2026-05-31

First end-to-end exercise of `backup.sh` and the restore procedure on `Legion-5`. Scope: USB target only, simulated by pointing `USB_REPO` at a local scratch directory (`~/restic-test-repo`). Azure target deferred — the `stbackuptheft` storage account and container are not yet provisioned.

**Measurements**

| Phase | Target | Measured | Gap |
|---|---|---|---|
| Backup wall-clock | n/a (informational) | 3.29 s | — |
| Restore wall-clock (Phase 1 of restore procedure) | ~10 min | 0.76 s | -9 min 59 s (well under) |
| Full RTO (file restore + runtime rebuild) | 90 min | not measured | runtime rebuild phase untested |

The file-restore portion is dramatically faster than the budget. The full 90-minute RTO target stays in place until a future drill measures the runtime rebuild phase (venv recreate, CUDA torch wheel install, Docker image pulls, container startup).

**Snapshot details**

- Repository ID: `d38d2cf7`
- Snapshot ID: `b54cb865`
- Files captured: 410
- Directories captured: 247
- Source size: 2.053 MiB raw, 1.714 MiB stored after dedup + compression
- Tags: `host=Legion-5`, `ts=2026-05-31T19:03:21Z`, `target=usb`

**Exclusion verification**

| Pattern | Expected | Observed |
|---|---|---|
| `venv/` | absent from restore | absent ✓ |
| `ai-model/models/*.pt` | absent from restore | absent ✓ |
| `backend/.env` | present in restore | present ✓ |

**Integrity check**

`restic check` on the repository: `no errors were found`.

**Gaps left open by this drill**

- Azure Blob target is unexercised. The `stbackuptheft` storage account, `backups` container, and `Storage Blob Data Contributor` role assignment are still pending a one-time manual provision.
- The runtime-rebuild phase of the restore procedure was not measured. Until it is, the 90-minute RTO is a budget, not a verified figure.
- The drill ran on the same laptop that took the backup. Recovery onto a fresh Linux install (the real disaster scenario) involves the entirety of `docs/01-linux-setup.md` before any restic call. That end-to-end version is the next drill worth running.
- No password-recovery rehearsal. The password manager copy of the repo password exists but has not been verified by performing a restore using only that copy.

**Procedure refinements**

- The `restic restore` output places the restored tree under `~/restore-drill/home/<user>/theft-detection-platform/`, not directly at `~/restore-drill/theft-detection-platform/`. The runbook's "Phase 2 — Promote to live" already accounts for this with `mv ~/restore/home/$USER/theft-detection-platform ~/`, but it's worth a note: the absolute-path preservation is by design, not a bug.
- No procedure changes needed. Script, excludes, and restore steps work as written.