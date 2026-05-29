# dev environment

Terraform root for the dev environment. State lives in the Azure
backend created by `scripts/bootstrap-backend.sh`.

Right now this directory only wires the backend. Provider config,
the resource-group module call, and the rest of the dev stack land
in a follow-up.

## First-time setup

You need an active `az login` session. The backend authenticates
through Azure AD, not storage account keys.

```bash
cd infrastructure/terraform/environments/dev
terraform init
```

That command does four things:

1. Downloads the azurerm provider (~4.0).
2. Reaches the storage account `sttfstatetheft` in `rg-tfstate-theft`.
3. Creates or opens the `dev.tfstate` blob inside the `tfstate` container.
4. Writes `.terraform.lock.hcl` (commit it) and `.terraform/` (gitignored).

## State locking

Locking is automatic. The azurerm backend takes a blob lease on
`dev.tfstate` while plan or apply is running. A second run from
another machine waits until the lease releases.

## Day-to-day

```bash
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

No resources are defined here yet, so plan and apply are no-ops
until the env root gets wired up.