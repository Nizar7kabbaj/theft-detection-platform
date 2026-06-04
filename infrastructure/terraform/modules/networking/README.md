# Networking module

Azure virtual network module. Takes an address space and an optional set of subnets, NSGs, and private DNS zones.

## What it creates

- One virtual network with the address space the caller declares
- One subnet per entry in the `subnets` map
- One NSG per subnet that opts in, attached to that subnet
- One private DNS zone per entry in `private_dns_zones`, each linked to the VNet

A call with only an address space produces a bare VNet. The subnets, NSGs, and DNS zones populate when the caller declares them.

## Usage

```hcl
module "networking" {
  source = "../../modules/networking"

  name                = "vnet-theft-detection-dev"
  resource_group_name = module.resource_group.name
  location            = "francecentral"
  environment         = "dev"

  address_space = ["10.0.0.0/16"]

  subnets = {
    workload = {
      address_prefixes = ["10.0.1.0/24"]
    }
    private-endpoints = {
      address_prefixes                  = ["10.0.2.0/24"]
      private_endpoint_network_policies = "Disabled"
    }
  }

  private_dns_zones = [
    "privatelink.vaultcore.azure.net",
  ]

  tags = {
    owner = "platform"
  }
}
```

## Inputs

| Name | Type | Default | Required |
|---|---|---|---|
| name | string | - | yes |
| resource_group_name | string | - | yes |
| location | string | `francecentral` | no |
| environment | string | - | yes |
| project | string | `theft-detection` | no |
| address_space | list(string) | - | yes |
| subnets | map(object) | `{}` | no |
| private_dns_zones | list(string) | `[]` | no |
| tags | map(string) | `{}` | no |

### Subnet object

| Field | Type | Default | Notes |
|---|---|---|---|
| address_prefixes | list(string) | - | required |
| service_endpoints | list(string) | `[]` | e.g. `Microsoft.Storage` |
| private_endpoint_network_policies | string | `Enabled` | set to `Disabled` for subnets that host private endpoints |
| delegation | object | `null` | one subnet delegation block when needed |
| create_nsg | bool | `true` | set false to skip NSG creation for this subnet |
| security_rules | list(object) | `[]` | NSG rules attached to the subnet's NSG |

## Outputs

| Name | Type | Notes |
|---|---|---|
| vnet_id | string | VNet resource ID |
| vnet_name | string | VNet name |
| vnet_address_space | list(string) | VNet address space |
| subnet_ids | map(string) | keyed by subnet name |
| subnet_address_prefixes | map(list(string)) | keyed by subnet name |
| nsg_ids | map(string) | keyed by subnet name, only for subnets with `create_nsg = true` |
| private_dns_zone_ids | map(string) | keyed by zone name |

## NSG defaults

The module adds no custom NSG rules. Azure attaches built-in default rules to every NSG that already deny all inbound traffic from the internet and allow traffic within the VNet. A subnet with `create_nsg = true` and an empty `security_rules` list is closed on day one. Open ports by adding entries to `security_rules`.

## Private DNS zones

Each zone in `private_dns_zones` lands in the same resource group as the VNet and links back to it. The link sets `registration_enabled = false` because privatelink zones resolve private endpoint hostnames, not workload DNS.

When a later module needs a private endpoint (Key Vault, Blob, Redis), pass the matching zone name here first, then reference `module.networking.private_dns_zone_ids["privatelink.vaultcore.azure.net"]` from the consumer module.

## Notes

- The module declares `required_providers` but no `provider` block. Provider config belongs to the environment root that calls the module.
- The module does not commit its own `.terraform.lock.hcl`. The lock file lives in the environment root.
- Subnet delegations and NSG security rules are dynamic blocks in `main.tf` so empty inputs produce empty blocks instead of errors.
