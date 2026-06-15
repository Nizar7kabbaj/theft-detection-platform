data "azurerm_client_config" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
    owner       = var.owner
  }
}

module "resource_group" {
  source = "../../modules/resource-group"

  name        = "rg-${local.name_prefix}"
  location    = var.location
  environment = var.environment
  project     = var.project
  tags        = local.common_tags
}

module "networking" {
  source = "../../modules/networking"

  name                = "vnet-${local.name_prefix}"
  resource_group_name = module.resource_group.name
  location            = var.location
  environment         = var.environment
  project             = var.project
  tags                = local.common_tags

  address_space = ["10.20.0.0/16"]

  subnets = {
    app = {
      address_prefixes  = ["10.20.1.0/24"]
      service_endpoints = ["Microsoft.KeyVault", "Microsoft.Storage"]
      create_nsg        = true
      security_rules    = []
    }
    data = {
      address_prefixes                  = ["10.20.2.0/24"]
      service_endpoints                 = ["Microsoft.KeyVault", "Microsoft.Storage"]
      private_endpoint_network_policies = "Disabled"
      create_nsg                        = true
      security_rules                    = []
    }
  }

  private_dns_zones = [
    "privatelink.vaultcore.azure.net",
  ]
}

module "security" {
  source = "../../modules/security"

  name                = "kv-theft-${var.environment}-${random_string.kv_suffix.result}"
  resource_group_name = module.resource_group.name
  location            = var.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  environment         = var.environment
  project             = var.project
  tags                = local.common_tags

  sku_name                      = "standard"
  soft_delete_retention_days    = 7
  purge_protection_enabled      = false
  enable_rbac_authorization     = true
  public_network_access_enabled = false

  network_acls_default_action = "Deny"
  network_acls_bypass         = "AzureServices"
  network_acls_ip_rules       = []
  network_acls_virtual_network_subnet_ids = [
    module.networking.subnet_ids["app"],
  ]
}

resource "random_string" "kv_suffix" {
  length  = 5
  upper   = false
  special = false
  numeric = true

  keepers = {
    project     = var.project
    environment = var.environment
  }
}
