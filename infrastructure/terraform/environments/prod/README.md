# environments/prod

Skeleton. No `terraform apply` has run against this directory. No Azure resources exist from this config.

The files mirror `environments/dev/` so that the prod wiring is already laid down when the hardening tickets that prod actually needs start landing. Anyone reviewing prod against dev should see a small, readable diff instead of a wall of new code.

## Files

- `backend.tf` — version pins for Terraform and providers, plus the remote state backend pointed at `prod.tfstate` in the shared state storage account.
- `providers.tf` — azurerm provider configuration. Byte-for-byte identical to dev. Provider features are not environment-specific.
- `main.tf` — three module calls: resource group, networking, security. Same module wiring as dev, with prod-shaped inputs.
- `variables.tf` — four inputs (`environment`, `project`, `location`, `owner`), all defaulted. Validation is tighter than dev.
- `outputs.tf` — ten outputs covering the resource group, virtual network, subnets, private DNS zones, and Key Vault. Same shape as dev.
- `terraform.tfvars.example` — documents the four knobs at their default values. The real `terraform.tfvars` is gitignored.

## What differs from dev

| Knob | Dev | Prod | Why |
|---|---|---|---|
| VNet address space | `10.20.0.0/16` | `10.30.0.0/16` | Non-overlapping space leaves room for staging or hub-spoke peering later without re-IPing prod. |
| Key Vault SKU | `standard` | `premium` | HSM-backed key option available when a real secret needs it. Premium costs nothing until an HSM key operation runs. |
| Soft-delete retention | 7 days | 90 days | 90 is the maximum the resource accepts. Cheap insurance — costs nothing while the vault is alive. |
| Environment validation | `dev` / `staging` / `prod` allowed | `prod` only | This root cannot legitimately deploy anything other than prod. Validation prevents a fat-finger from creating a `dev`-tagged resource group inside prod state. |
| Location validation | none | `spaincentral` only | Azure for Students blocks Microsoft.Storage in francecentral. Wrong region in prod is a worse failure than in dev. |

Everything else matches dev: `purge_protection_enabled = false`, `public_network_access_enabled = false`, the `random_string` Key Vault suffix, network ACLs default-deny, the data subnet with `private_endpoint_network_policies = "Disabled"`. The cost-zero destroy thesis still applies here while the skeleton stays unapplied.

## Purge protection note

`purge_protection_enabled` is `false` for the same reason it is `false` in dev: a destroy-then-recreate cycle needs the vault name reusable inside the 7-90 day soft-delete window. When a real secret lands in this vault — separate ticket, future PR — the flag flips to `true` and this README updates to match. Until then, the skeleton stays cheap to tear down.

## What is deliberately not here

Private endpoints. Diagnostic settings. Microsoft Defender for Cloud. Real NSG security rules. Identity wiring and RBAC role assignments. All of those are tracked separately and land in their own PRs before this directory ever sees an apply.

The Key Vault network ACLs in this skeleton are configured to allow the `app` subnet via service endpoint — same as dev. That is not the prod-grade posture; that is the dev-grade posture copied over so the skeleton is structurally complete. The hardening ticket replaces the service-endpoint path with a private endpoint and removes the subnet allow-list.

## Running it

Not yet. When the hardening prerequisites have landed:
```
cd infrastructure/terraform/environments/prod
terraform init
terraform plan
terraform apply
```
Backend auth is AAD via the active `az login` session. No storage keys, no service principals on disk. The helper scripts under `infrastructure/terraform/scripts/` work against this directory the same way they work against dev.