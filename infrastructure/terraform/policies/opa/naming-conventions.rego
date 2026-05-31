package terraform.naming

import rego.v1


deny contains msg if {
	resource := input.resource_changes[_]
	resource.change.actions[_] != "delete"
	location := resource.change.after.location
	location != null
	location != "global"
	location != "spaincentral"
	msg := sprintf(
		"%s at %s uses location %q. Project resources must use spaincentral.",
		[resource.type, resource.address, location],
	)
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	name := resource.change.after.name
	name != null
	count(name) > 24
	msg := sprintf(
		"key vault at %s has name %q with %d characters. Azure caps key vault names at 24.",
		[resource.address, name, count(name)],
	)
}

type_prefix := {
	"azurerm_resource_group": "rg-",
	"azurerm_virtual_network": "vnet-",
	"azurerm_network_security_group": "nsg-",
	"azurerm_key_vault": "kv-",
	"azurerm_private_dns_zone_virtual_network_link": "link-",
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.change.actions[_] != "delete"
	prefix := type_prefix[resource.type]
	name := resource.change.after.name
	name != null
	not startswith(name, prefix)
	msg := sprintf(
		"%s at %s has name %q. Names for this type must start with %q.",
		[resource.type, resource.address, name, prefix],
	)
}