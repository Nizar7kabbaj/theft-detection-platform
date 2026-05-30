output "resource_group_name" {
  description = "Name of the resource group holding all dev resources."
  value       = module.resource_group.name
}

output "resource_group_id" {
  description = "Resource ID of the dev resource group."
  value       = module.resource_group.id
}

output "resource_group_location" {
  description = "Azure region of the dev resource group."
  value       = module.resource_group.location
}

output "vnet_id" {
  description = "ID of the dev virtual network."
  value       = module.networking.vnet_id
}

output "vnet_name" {
  description = "Name of the dev virtual network."
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
  description = "Resource ID of the dev Key Vault."
  value       = module.security.id
}

output "key_vault_name" {
  description = "Name of the dev Key Vault."
  value       = module.security.name
}

output "key_vault_uri" {
  description = "DNS URI of the dev Key Vault. Read by applications that fetch secrets."
  value       = module.security.vault_uri
}