# Terraform

Infrastructure-as-code for the Azure side of the real-time theft detection
platform. This directory is the Terraform root.

## Status

Scaffold and three modules in progress. Each module and environment is built
by its own ticket. A directory holding only a `.gitkeep` is a placeholder
waiting for the ticket that fills it.

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

The pattern: write a module once, call it from both `dev` and `prod` with
different inputs. `dev` stays cheap; `prod` is sized for real use.

## Target subscription

- Subscription: Azure for Students
- Resource group: `rg-theft-detection`
- Region: France Central

The resource group already exists and survived the OS migration. Terraform
manages resources inside it.

## Cost discipline

This subscription runs on a fixed student credit. The rule is simple: when you
stop demoing, tear it down.

```bash
cd infrastructure/terraform/environments/dev
terraform destroy -auto-approve
```

Bring it back in a few minutes when needed:

```bash
terraform apply -auto-approve
```

Destroy whenever the stack sits idle for more than a day. Never provision a
Premium tier of anything. Basic, Consumption, and Serverless only.

## What is safe to commit

`.gitignore` blocks the dangerous files: state (`*.tfstate`) holds secrets in
plaintext, `.terraform/` is a local cache, and `*.tfvars` files often carry
credentials. Two files are kept on purpose: `.terraform.lock.hcl` pins provider
versions for repeatable builds, and any `*.tfvars.example` documents the
variables a real `*.tfvars` must supply.

Never commit a real `*.tfvars` or any `*.tfstate`. If you need to share what
variables an environment expects, commit a `.tfvars.example` with placeholder
values.

## Prerequisites

- Terraform 1.15.5 or later
- Azure CLI 2.86.0 or later, logged in (`az login`)
- Access to the Azure for Students subscription above