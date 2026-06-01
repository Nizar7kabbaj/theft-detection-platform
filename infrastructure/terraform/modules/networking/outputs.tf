output "vnet_id" {
  description = "ID of the virtual network."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Name of the virtual network."
  value       = azurerm_virtual_network.this.name
}

output "vnet_address_space" {
  description = "Address space of the virtual network."
  value       = azurerm_virtual_network.this.address_space
}

output "subnet_ids" {
  description = "Map of subnet name to subnet ID."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.id }
}

output "subnet_address_prefixes" {
  description = "Map of subnet name to its address prefixes."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.address_prefixes }
}

output "nsg_ids" {
  description = "Map of subnet name to its NSG ID (only for subnets where the module created an NSG)."
  value       = { for name, nsg in azurerm_network_security_group.this : name => nsg.id }
}

output "private_dns_zone_ids" {
  description = "Map of private DNS zone name to its ID."
  value       = { for name, zone in azurerm_private_dns_zone.this : name => zone.id }
}