# Terraform Foundation

This doc covers the infrastructure-as-code layout for the theft-detection-platform: where the Terraform code lives, what each module owns, how state persists across `terraform destroy`, how authentication works, and the design rule that keeps the whole stack at zero cost when idle.

## Repo layout

All Terraform code lives under `infrastructure/terraform/`:

```
infrastructure/terraform/
├── environments/
│   ├── dev/          # spaincentral, applied + destroyed end-to-end
│   └── prod/         # spaincentral, skeleton only, no apply yet
├── modules/
│   ├── resource-group/
│   ├── networking/
│   └── security/
├── policies/
│   ├── opa/          # *.rego — enforced via conftest
│   ├── sentinel/     # *.sentinel — spec-only, paired with the rego
│   └── README.md
└── scripts/          # plan / apply / destroy helpers
```

Two split rules govern this layout:

- **Modules are reusable, environments are concrete.** A module declares variables, resources, and outputs. An environment root sets values for those variables and calls the modules. Same module, different envs, different inputs.
- **Modules do not pin a provider.** Each module declares `required_providers` in `versions.tf` but never opens a `provider` block of its own. Provider config belongs to the env root. Modules also do not ship a `.terraform.lock.hcl` — the lock file pins the dependency graph for a real deployment, which only the env root has.

## The three modules

| Module | Owns |
|---|---|
| `resource-group` | One `azurerm_resource_group` plus standard tags |
| `networking` | VNet, subnets, NSGs, subnet-NSG associations, private DNS zones, VNet links |
| `security` | Key Vault (RBAC mode), `network_acls` default-deny, public access disabled |

Module defaults set `francecentral` as the location, but every environment root passes `spaincentral` and wins. The default exists so a future portable consumer of these modules doesn't have to know the project history; the active deployment uses `spaincentral` end-to-end because Azure for Students blocks `Microsoft.Storage` in `francecentral`.

A few module-side rules worth knowing:

- The Key Vault name is computed: `kv-theft-<env>-<random_string>`. The random suffix solves the global-uniqueness requirement without forcing a manual rename per environment.
- `purge_protection_enabled = false` on the vault. This is non-negotiable. Purge protection means the vault sticks around for 7 to 90 days after destroy, which violates the zero-cost-on-destroy rule (see below). The four checkov suppressions around purge protection trace back to this.
- NSG-to-subnet associations live in `modules/networking/main.tf` alongside the subnet definitions. The `checkov` CKV2_AZURE_31 finding is a false positive — checkov can't trace the association across module boundaries.

## Environments

Two environment roots, same shape:

```
environments/<env>/
├── main.tf              # module calls
├── variables.tf         # env inputs
├── outputs.tf           # resolved IDs for downstream consumers
├── versions.tf          # provider pins, backend block
├── terraform.tfvars     # gitignored, real values
├── terraform.tfvars.example   # committed, placeholder values
└── .terraform.lock.hcl  # committed, version-pinned
```

`dev` is wired, applied, and destroys clean. `prod` is skeleton only with a few deltas: VNet at `10.30.0.0/16`, Key Vault `sku_name = premium`, `soft_delete_retention_days = 90`, environment validation locked to `["prod"]`, location validation locked to `["spaincentral"]`. Nothing has been applied against `prod` yet.

## Remote state backend

The backend is an Azure Storage Account that lives outside the project resource group:

- Resource group: `rg-tfstate-theft` (region: `spaincentral`)
- Storage account: `sttfstatetheft`
- Container: `tfstate`
- One blob per environment: `dev.tfstate`, `prod.tfstate`

The state backend survives `terraform destroy`. The project resource groups (`rg-theft-dev-*`, future `rg-theft-prod-*`) destroy to zero. The state storage account does not. This is intentional — losing state means losing the ability to reconcile the next apply with what's actually on Azure. Manual teardown only, never through `terraform destroy`.

State has no latency requirement, so it doesn't need to share a region with the project resources.

## AAD auth, no storage keys

Every Azure provider call and every backend interaction uses Azure AD authentication:

- `use_azuread_auth = true` on the backend block
- No `access_key` or `sas_token` in any config
- `az login` provides the credentials, the provider picks them up

The signed-in user needs `Storage Blob Data Contributor` on the state storage account. RBAC role assignment is a one-time setup, not part of Terraform.

The "no storage keys" rule eliminates a class of secret-leak risk. Keys would otherwise live in `.tfvars`, environment variables, or CI config, each of which is a leak vector.

## Subscription guard

A gitignored `.tf-env` at the repo root sets `AZURE_SUBSCRIPTION_ID`. The helper scripts source it before any `terraform` call, which pins the run to the intended subscription.

```bash
# .tf-env (gitignored)
export AZURE_SUBSCRIPTION_ID="<your-subscription-uuid>"
```

`.tf-env.example` is committed as the template. The guard prevents the most expensive kind of mistake: applying against the wrong subscription because the CLI was last authenticated against a different one.

## `terraform.tfvars` vs `terraform.tfvars.example`

- `terraform.tfvars` is gitignored. Real values: project tags, environment name, location, anything specific to the current deployment.
- `terraform.tfvars.example` is committed. Placeholder values, same keys, serves as the contract for a fresh clone.

Recreating `terraform.tfvars` from `.example` after a clone is the same flow as recreating `backend/.env` from `backend/.env.example`.

## Helper scripts

Three thin wrappers under `infrastructure/terraform/scripts/`:

- `tf-plan.sh <env>` — sources `.tf-env`, runs `terraform plan` against the env, writes `tfplan` and `tfplan.json`
- `tf-apply.sh <env>` — sources `.tf-env`, applies the saved plan
- `tf-destroy.sh <env>` — sources `.tf-env`, runs `terraform destroy` with confirmation

Each script does the same three things:

1. Source `.tf-env` and fail loudly if `AZURE_SUBSCRIPTION_ID` is empty
2. `cd` into the right env directory (running terraform from the repo root would silently target an empty directory)
3. Run the terraform command

The scripts exist because the manual flow has too many ways to get it wrong: forgetting to `cd`, forgetting to source the guard, forgetting to save the plan before apply.

## Policy-as-code

Three OPA Rego files under `policies/opa/` enforce rules on every commit through the `conftest` pre-commit hook:

- `naming-conventions.rego` — region must be `spaincentral`, Key Vault names cap at 24 characters, resource names must start with the type prefix
- `cost-control.rego` — no `azurerm_management_lock` ever, Key Vault `purge_protection_enabled` must stay `false`, premium vault SKU allowed only when the environment tag is `prod`
- `security-baseline.rego` — Key Vault `public_network_access_enabled` must be `false`, `network_acls` default action must be `Deny`, RBAC authorization must be on, required tags (`project`, `environment`, `managed_by`) on every taggable resource

Three Sentinel files mirror the same rules as portable specs. Sentinel is HashiCorp's policy language for Terraform Cloud. The project doesn't use Terraform Cloud, so the Sentinel files document intent rather than execute.

Full rationale and the OPA vs Sentinel split lives in `policies/README.md`.

## Zero-cost-on-destroy

This is the first-class design constraint that shapes every other decision in the foundation. When `terraform destroy` runs against an environment, the Azure for Students subscription must charge zero dollars per day until the next apply.

Practical consequences:

- Key Vault `purge_protection_enabled = false`. Purge protection forces a 7-to-90-day retention window during which the vault still incurs charges, which violates the rule.
- `soft_delete_retention_days = 7` in `dev`. Minimum allowed by the provider.
- No `azurerm_management_lock` anywhere. Locks would block `terraform destroy`.
- The state storage account is the only resource the project deliberately leaves running. It charges fractions of a cent per month for the state blobs.
- Empty resource groups are free. The project resource group can stay around after destroy without cost.

The dev environment proves the rule end-to-end: 12 resources apply in `spaincentral`, then destroy to zero, then `az group show` returns `ResourceGroupNotFound`. The round-trip charges nothing.

## Other docs in this folder

- `docs/01-linux-setup.md` — local dev environment for this stack
- `docs/03-pre-commit.md` — terraform hook install, tool pins, suppression rationale
- `docs/04-disaster-recovery.md` — backup script, restore runbook, drill log