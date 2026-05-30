# dev environment

Terraform root for the dev environment. Wires three modules — resource-group, networking, security — into a single deployable stack.

## What it builds

One resource group, one virtual network with two subnets and one private DNS zone, one Key Vault. All in spaincentral, all tagged `project = theft-detection`, `environment = dev`, `managed_by = terraform`.

```
rg-theft-detection-dev
├── vnet-theft-detection-dev (10.20.0.0/16)
│   ├── app subnet  (10.20.1.0/24, NSG, service endpoints: KeyVault + Storage)
│   ├── data subnet (10.20.2.0/24, NSG, PE network policies disabled)
│   └── privatelink.vaultcore.azure.net (private DNS zone, linked to vnet)
└── kv-theft-dev-XXXXX (RBAC auth, public network disabled, default-deny ACLs)
```

The Key Vault name carries a 5-character random suffix because vault names are globally unique across Azure. Without it, a destroy-and-recreate cycle would collide with the soft-deleted name for 7 days.

## Region

Everything runs in spaincentral. The Azure for Students allowlist blocks Microsoft.Storage in francecentral, and splitting regions forces every storage-adjacent resource to handle cross-region wiring later. Keeping the whole dev stack in one region is simpler.

## Prerequisites

- Azure CLI installed and `az login` complete
- `.tf-env` at repo root with `AZURE_SUBSCRIPTION_ID` set (see `.tf-env.example`)
- Terraform >= 1.10

## First run

​```bash
./infrastructure/terraform/scripts/tf.sh dev init
./infrastructure/terraform/scripts/tf.sh dev validate
./infrastructure/terraform/scripts/tf.sh dev plan
./infrastructure/terraform/scripts/tf.sh dev apply
​```

The wrapper handles the subscription guard, the cd-into-env-directory step, and the saved-plan flow. `init` downloads providers, reaches the backend in spaincentral, and locks `dev.tfstate`.

`plan` writes a tfplan file. `apply` consumes that file and deletes it on success. Plans older than 30 minutes prompt before applying.

## Variables

All four have defaults. Override via `terraform.tfvars` (gitignored) if needed:

| Variable | Default | Purpose |
|---|---|---|
| `environment` | `dev` | Used in resource names and tags |
| `project` | `theft-detection` | Used in resource names and tags |
| `location` | `spaincentral` | Azure region |
| `owner` | `nizar` | Owner tag value |

## Outputs

`terraform output` surfaces the resource group, vnet, subnet IDs, private DNS zone IDs, and the Key Vault id / name / uri. Later work reads these when wiring backend services and private endpoints.

## Authentication

The azurerm provider reads the active `az login` session. No subscription ID, no tenant ID, no client secret in any committed file. `use_azuread_auth = true` and `storage_use_azuread = true` mean even the backend uses AAD instead of storage account keys.

## Cost

Zero when destroyed. The vault ships with `purge_protection_enabled = false` and the provider has `purge_soft_delete_on_destroy = true`, so destroy fully removes the vault instead of leaving a soft-deleted name lock. The resource group has `prevent_deletion_if_contains_resources = false` so the RG comes down cleanly even mid-teardown.

## Teardown

​```bash
./infrastructure/terraform/scripts/tf.sh dev destroy
​```

Type `dev` at the prompt to confirm. The state backend (rg-tfstate-theft / sttfstatetheft) survives — it was created out-of-band and is not managed by this stack.