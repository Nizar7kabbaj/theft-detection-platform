# Terraform

Infrastructure-as-code for the Azure side of the theft detection platform.
This directory is the Terraform root.

## Status

Scaffold and three modules in progress. Each module and each environment lands
incrementally. A directory holding only a `.gitkeep` is a placeholder waiting
for the work that fills it.

## Layout

```
infrastructure/terraform/
├── environments/
│   ├── dev/      # dev root config, wires modules together
│   └── prod/     # prod root config
├── modules/
│   ├── resource-group/   # resource group + naming convention
│   ├── networking/       # VNet, subnets, NSGs, private DNS zones
│   └── security/         # Key Vault, managed identities, RBAC
├── policies/
│   ├── sentinel/   # Sentinel policy-as-code
│   └── opa/        # Open Policy Agent / Conftest rules
├── scripts/        # bootstrap and helper scripts
├── .gitignore
└── README.md
```

## How it fits together

Modules under `modules/` are reusable building blocks. They define resources
but do not pick an environment. An environment under `environments/` calls the
modules with concrete values (region, sizes, names) and holds the backend and
provider configuration for that environment.

Write a module once, call it from both `dev` and `prod` with different inputs.
`dev` stays cheap. `prod` is sized for whatever workload it ends up carrying.

## Target subscription

- Subscription: Azure for Students
- Region: Spain Central

Project resources and state both live in Spain Central. Azure for Students
allowlist blocks `Microsoft.Storage` in France Central, so splitting regions
would force every storage-adjacent resource to cross regions. Keeping the
whole dev stack in one region avoids that.

## Cost discipline

This subscription runs on a fixed student credit. Tear it down when you stop
demoing.

```bash
cd infrastructure/terraform/environments/dev
terraform destroy -auto-approve
```

Bring it back when needed:

```bash
terraform apply -auto-approve
```

Destroy whenever the stack sits idle for more than a day. Never provision a
Premium tier of anything. Basic, Consumption, and Serverless only.

`-auto-approve` is safe here because every resource in the dev environment
destroys to nothing billable. The state backend (resource group
`rg-tfstate-theft`, storage account `sttfstatetheft`) is excluded from this
and is torn down manually if ever needed.

## What is safe to commit

`.gitignore` blocks the dangerous files: state (`*.tfstate`) holds secrets in
plaintext, `.terraform/` is a local cache, and `*.tfvars` files often carry
credentials. Two things stay on purpose: `.terraform.lock.hcl` pins provider
versions for repeatable builds, and `*.tfvars.example` documents what
variables a real `*.tfvars` must supply.

Never commit a real `*.tfvars` or any `*.tfstate`. To share what variables an
environment expects, commit a `.tfvars.example` with placeholder values.

## Prerequisites

- Terraform >= 1.10 (lock file pins azurerm `~> 4.0`, currently v4.74.0)
- Azure CLI, logged in via `az login`
- Access to the Azure for Students subscription above
- `AZURE_SUBSCRIPTION_ID` exported from a gitignored `.tf-env` at repo root
