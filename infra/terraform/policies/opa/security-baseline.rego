package terraform.security

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	resource.change.after.public_network_access_enabled == true
	msg := sprintf(
		"key vault at %s has public_network_access_enabled = true. Vaults must ship with public access disabled.",
		[resource.address],
	)
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	acls := resource.change.after.network_acls[_]
	acls.default_action != "Deny"
	msg := sprintf(
		"key vault at %s has network_acls.default_action = %q. Default action must be Deny.",
		[resource.address, acls.default_action],
	)
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	resource.change.after.enable_rbac_authorization == false
	msg := sprintf(
		"key vault at %s has enable_rbac_authorization = false. Legacy access policies are not allowed.",
		[resource.address],
	)
}

required_tags := {"project", "environment", "managed_by"}

taggable_types := {
	"azurerm_resource_group",
	"azurerm_virtual_network",
	"azurerm_network_security_group",
	"azurerm_key_vault",
	"azurerm_private_dns_zone",
}

deny contains msg if {
	resource := input.resource_changes[_]
	taggable_types[resource.type]
	resource.change.actions[_] != "delete"
	tags := object.get(resource.change.after, "tags", {})
	missing := required_tags - {key | tags[key]}
	count(missing) > 0
	msg := sprintf(
		"%s at %s is missing required tags: %v",
		[resource.type, resource.address, missing],
	)
}
