# Pre-commit hooks

Pre-commit runs every commit through four passes: file hygiene, secret scanning, terraform validation, and Python supply-chain audit. Config lives at `.pre-commit-config.yaml`. Suppressions are in `.tfsec/config.yml` and `.checkov.yaml`. Lint rules are in `.tflint.hcl`.

## What runs on every commit

File hygiene from the `pre-commit/pre-commit-hooks` repo:

- `check-yaml` parses every YAML file and rejects syntax errors
- `trailing-whitespace` strips trailing spaces
- `end-of-file-fixer` enforces a single newline at EOF
- `check-merge-conflict` rejects commits containing unresolved `<<<<<<<` markers

The whitespace and EOF hooks skip `infrastructure/mongodb/mongod.conf` because mongod's parser treats the file's formatting as significant and the auto-fixes break the boot.

Secret scanning via `gitleaks` v8.30.1 against staged changes. A full-history scan returned zero findings when the hook landed, so the staged-scan default covers new work without re-scanning history on every commit.

Terraform stack:

- `terraform fmt` rewrites files to canonical formatting
- `tflint` against `.tflint.hcl`
- `tfsec` against `.tfsec/config.yml`
- `checkov` against `infrastructure/terraform/` with `.checkov.yaml`

Python supply-chain audit via `pip-audit` against `backend/requirements.txt`. Resolves the dependency tree, queries PyPI's vulnerability database, fails the commit if any pin has a known CVE.

## What runs manually

`conftest` against the OPA policies in `infrastructure/terraform/policies/opa/`. Manual because it needs a real `terraform plan -json` to evaluate.

## First-time setup on a fresh clone

Install the framework:

```bash
pip install --user pre-commit
```

Install gitleaks:

```bash
GITLEAKS_VERSION=8.30.1
curl -L -o /tmp/gitleaks.tar.gz "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
tar -xzf /tmp/gitleaks.tar.gz -C /tmp/
sudo mv /tmp/gitleaks /usr/local/bin/
rm /tmp/gitleaks.tar.gz
```

Install tflint:

```bash
curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
```

Install tfsec:

```bash
curl -s https://raw.githubusercontent.com/aquasecurity/tfsec/master/scripts/install_linux.sh | bash
```

Install checkov:

```bash
pip install --user checkov
```

Install conftest:

```bash
CONFTEST_VERSION=0.62.0
curl -L -o /tmp/conftest.tar.gz "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_x86_64.tar.gz"
tar -xzf /tmp/conftest.tar.gz -C /tmp/
sudo mv /tmp/conftest /usr/local/bin/
rm /tmp/conftest.tar.gz
```

pip-audit comes from the pypa repo via the pre-commit framework. No host-side install needed.

Wire it into git and run once against everything:

```bash
pre-commit install
pre-commit run --all-files
```

All auto-stage hooks should pass.

## Running conftest manually

From an environment directory after a successful plan:

```bash
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json
conftest test --policy ../../policies/opa tfplan.json
rm tfplan.binary tfplan.json
```

## Suppressed checks

- key vault purge protection and soft delete recoverability would keep the vault billing for 7 to 90 days after destroy, blocking a clean teardown
- private endpoint on the key vault is future work, out of scope here
- subnet-to-NSG association is a checkov false positive across module boundaries; the real association is in `modules/networking/main.tf`

## Updating hook versions

```bash
pre-commit autoupdate
```

Run, verify clean, commit the updated `.pre-commit-config.yaml`.
