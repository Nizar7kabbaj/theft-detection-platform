# Pre-commit hooks

Pre-commit runs the terraform stack through fmt, lint, security scanners, and policy checks before every commit. Config lives at `.pre-commit-config.yaml`. Suppressions are in `.tfsec/config.yml` and `.checkov.yaml`. Lint rules are in `.tflint.hcl`.

## What runs on every commit

- terraform fmt
- tflint
- tfsec
- checkov

## What runs manually

conftest, against the OPA policies in `infrastructure/terraform/policies/opa/`. Manual because it needs a real `terraform plan -json` to evaluate.

## First-time setup on a fresh clone

Install the framework:

    pip install --user pre-commit

tflint:

    curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

tfsec:

    curl -s https://raw.githubusercontent.com/aquasecurity/tfsec/master/scripts/install_linux.sh | bash

checkov:

    pip install --user checkov

conftest:

    CONFTEST_VERSION=0.62.0
    curl -L -o /tmp/conftest.tar.gz "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_x86_64.tar.gz"
    tar -xzf /tmp/conftest.tar.gz -C /tmp/
    sudo mv /tmp/conftest /usr/local/bin/
    rm /tmp/conftest.tar.gz

Wire it into git and run once against everything:

    pre-commit install
    pre-commit run --all-files

All four auto-stage hooks should pass.

## Running conftest manually

From an environment directory after a successful plan:

    terraform plan -out=tfplan.binary
    terraform show -json tfplan.binary > tfplan.json
    conftest test --policy ../../policies/opa tfplan.json
    rm tfplan.binary tfplan.json

## Suppressed checks

- key vault purge protection and soft delete recoverability conflict with the zero-cost-on-destroy rule
- private endpoint on the key vault is future work, out of scope here
- subnet-to-NSG association is a checkov false positive across module boundaries; the real association is in `modules/networking/main.tf`

## Updating hook versions

    pre-commit autoupdate

Run, verify clean, commit the updated `.pre-commit-config.yaml`.
