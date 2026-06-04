# Security module

Azure Key Vault for the theft detection platform.

## What this module does

Creates a single Key Vault. Nothing else — no secrets, no role assignments, no private endpoint, no diagnostic settings. Those land in later tickets when there's something real to wire.

The vault ships closed: public network access off, network ACL default action Deny, RBAC authorization on, purge protection off so `terraform destroy` works.

## Usage

```hcl
module "security" {
  source = "../../modules/security"

  name                = "kv-theft-detection-dev"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  environment         = "dev"
}
```

## Inputs

| Name | Type | Default | Notes |
|---|---|---|---|
| name | string | — | 3-24 chars, globally unique, alphanumeric + hyphens |
| resource_group_name | string | — | from the resource-group module |
| location | string | francecentral | inherit from the RG |
| tenant_id | string | — | from `data.azurerm_client_config.current` |
| environment | string | — | dev or prod |
| project | string | theft-detection | for tagging |
| tags | map(string) | {} | merged on top of module defaults |
| sku_name | string | standard | premium only for HSM-backed keys |
| soft_delete_retention_days | number | 7 | minimum allowed by Azure |
| purge_protection_enabled | bool | false | true blocks destroy until retention expires |
| enable_rbac_authorization | bool | true | RBAC, not legacy access policies |
| public_network_access_enabled | bool | false | vault closed by default |
| network_acls_default_action | string | Deny | |
| network_acls_bypass | string | AzureServices | |
| network_acls_ip_rules | list(string) | [] | |
| network_acls_virtual_network_subnet_ids | list(string) | [] | from the networking module |

## Outputs

| Name | Notes |
|---|---|
| id | vault resource ID |
| name | vault name |
| vault_uri | DNS URI applications use to read secrets |

## Notes

- No `provider` block. The module declares `required_providers` only; the caller configures the provider.
- `azurerm_key_vault` does not support an `identity` block. Key Vault is itself an identity store. Managed identities that need vault access are wired by the caller with `azurerm_role_assignment` in later tickets.
- Soft delete cannot be disabled in azurerm 4.x. 7 days is the minimum retention and what dev environments want for fast destroy and recreate cycles.
