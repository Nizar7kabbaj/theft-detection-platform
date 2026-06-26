output "resource_group_name" {
  description = "Name of the resource group holding all prod resources."
  value       = module.resource_group.name
}

output "resource_group_id" {
  description = "Resource ID of the prod resource group."
  value       = module.resource_group.id
}

output "resource_group_location" {
  description = "Azure region of the prod resource group."
  value       = module.resource_group.location
}

output "vnet_id" {
  description = "ID of the prod virtual network."
  value       = module.networking.vnet_id
}

output "vnet_name" {
  description = "Name of the prod virtual network."
  value       = module.networking.vnet_name
}

output "subnet_ids" {
  description = "Map of subnet name to subnet ID."
  value       = module.networking.subnet_ids
}

output "private_dns_zone_ids" {
  description = "Map of private DNS zone name to ID."
  value       = module.networking.private_dns_zone_ids
}

output "key_vault_id" {
  description = "Resource ID of the prod Key Vault."
  value       = module.security.id
}

output "key_vault_name" {
  description = "Name of the prod Key Vault."
  value       = module.security.name
}

output "key_vault_uri" {
  description = "DNS URI of the prod Key Vault. Read by applications that fetch secrets."
  value       = module.security.vault_uri
}
