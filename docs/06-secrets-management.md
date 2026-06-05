# Secrets management

Two layers protect secrets in this project. Pre-commit hooks block secrets from reaching git. A fixed rotation procedure keeps generated values out of terminal output and shell history. Encrypted environment files and cloud secret stores defer to later architectural work, with reasoning below.

## Scope

Three categories of secret material exist today:

- **Local development credentials.** Database passwords, signing keys, exporter credentials needed to run the stack on a laptop. Live in `backend/.env`, gitignored. Never in tracked content.
- **Local service config with embedded auth.** Redis `requirepass`, MongoDB monitoring user definitions, Grafana admin password. Live in service config files under `infrastructure/<service>/`, root-owned, mode 640, gitignored. A `.example` template ships alongside with placeholders.
- **Cloud credentials.** MongoDB Atlas connection string. Same `backend/.env` location and same rotation cadence as local credentials.

Out of scope here: Azure Key Vault material, production-side secret distribution, runtime secret injection in container orchestration. Those land with the microservices split when the architecture justifies the tooling.

## Detection layer

Two kinds of check run on every commit through `.pre-commit-config.yaml`.

### Gitleaks

Pinned to `v8.30.1`. Runs against the staged diff and aborts the commit if any of the default ruleset's 100+ patterns match — AWS access tokens, GitHub PATs, Slack tokens, Stripe live keys, private SSH keys, JWT-shaped strings, and others.

Two verifications established the layer works:

- **History scan.** A one-time `gitleaks git --log-opts="--all"` swept every patch-bearing commit in the repo (50 commits, ~2 MB of tracked content across all refs). Zero findings. The JSON report is archived at `~/security-scans/` outside the repo.
- **Planted-secret test.** A constructed AKIA-pattern string was committed against a clean branch. Gitleaks fired with `RuleID: aws-access-token`, exit code 1, commit aborted. The planted file never reached a commit hash.

The zero-finding history scan matters because it scopes downstream rotation work. Past credential exposures reached terminal output, not git history. Rotation alone closes those exposures. No `git filter-repo` rewrite is needed for that reason.

### Standard hygiene

Four hooks from `pre-commit/pre-commit-hooks` v6.0.0:

- `check-yaml` parses every YAML file before commit. Catches malformed config that would later break pipelines.
- `trailing-whitespace` strips trailing spaces.
- `end-of-file-fixer` ensures every text file ends in a newline.
- `check-merge-conflict` blocks accidental commits with unresolved conflict markers.

Both `trailing-whitespace` and `end-of-file-fixer` exclude `infrastructure/mongodb/mongod.conf`. That file is root-owned and read by the mongod container; its permission model belongs to the container, not the developer. The exclusion does not exempt the file from gitleaks — gitleaks scans the staged diff regardless of file ownership on disk.

## Rotation

The procedure for any credential follows the same five steps, applied per-service:

1. Generate the new value with `openssl rand`. Pipe directly to a temp file created via `mktemp` with `chmod 600`. The value never appears in terminal output.
2. Hash-verify the temp file against a hash recorded in the password manager. Detects paste corruption without ever displaying the value.
3. Update the live service. The mechanism varies: `mongosh updateUser` for Mongo users, `redis.conf` rewrite plus container recreate for Redis, `.env` replace plus container recreate for Grafana.
4. Verify end-to-end. The dependent scrape target returns to `up=1`, the backend reconnects, the login works — whichever signal applies.
5. Record the new value and its hash in the password manager. Shred the temp file.

Three rules tighten the procedure:

- **Never echo a secret.** No `cat .env`, no `echo $VAR`, no `docker compose config` without explicit `grep -v` filters for every known secret variable name. Prefer `--no-interpolate` where the command supports it.
- **Never visually inspect.** Two strings that look identical at a glance differ by a single character often enough to matter. Hash-compare is the only correct verification.
- **Never restate a leaked value.** Once a value reaches terminal output or shell history, that value is dead. Generate a new one and rotate before continuing.

## Service grouping in `.env`

Each service gets its own block in `backend/.env`, separated by a comment header:

```
# MongoDB (local + Atlas)
MONGODB_URL_LOCAL=...
MONGODB_URL=...

# Redis (local)
REDIS_PASSWORD_LOCAL=...
REDIS_URL_LOCAL=...

# Prometheus exporters
MONGO_EXPORTER_USERNAME=...
MONGO_EXPORTER_PASSWORD=...

# Grafana
GF_SECURITY_ADMIN_PASSWORD=...

# FastAPI
SECRET_KEY=...
```

Two reasons for the grouping. First, rotation is atomic per service: when the Redis password changes, every line that depends on it (the URL with embedded credentials, the exporter credential, the healthcheck command) lives in one block and gets updated together. Second, when the backend monolith splits into microservices, each block becomes the environment for its own service with no untangling needed.

## Atlas

MongoDB Atlas is the planned production target, kept alongside the local Mongo container used for daily development. The Atlas connection string lives in `backend/.env` under the same rotation cadence as local credentials. Future work moves Atlas credentials into a cloud secret store once the microservices split lands and a secret-distribution mechanism exists for the new architecture.

## Deferred work

**Encrypted environment files via sops + age.** Defers to the microservices-split epic. Encrypting a temporary monolith's environment file solves a problem that disappears the moment the monolith is split into per-service deployments with proper secret distribution. The git-layer protection here survives the architectural change; the encryption layer would be redesigned during the split.

**History rewrite via `git filter-repo`.** Scoped into the trained-model-purge epic, which already plans a destructive history rewrite for the model binary. The history scan above returned zero secret findings, so no secret-purge motivation applies. Filter-repo runs once or not at all; bundling it preemptively is not necessary.

## Verifying the layer works

Install hooks once per clone:

```bash
pre-commit install
```

Run all hooks against the full repo:

```bash
pre-commit run --all-files
```

Test that gitleaks blocks a planted secret. Construct any AKIA-prefix string of 20 total characters drawn from `[A-Z2-7]` that does not end in `EXAMPLE` (the gitleaks default ruleset allowlists canonical AWS documentation values). Drop the string in a throwaway file with an `aws_key = "..."` assignment, stage it, and try to commit. The `Detect hardcoded secrets` hook should fail with exit code 1 and report `RuleID: aws-access-token`. Clean up the planted file before continuing.

Re-run the history scan against the full repo any time before a security review:

```bash
gitleaks git --no-banner --redact --log-opts="--all" .
```

Findings inform whether additional remediation is needed beyond rotation.
