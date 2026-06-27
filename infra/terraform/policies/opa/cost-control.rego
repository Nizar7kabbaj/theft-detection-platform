package terraform.cost

import rego.v1

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_management_lock"
	resource.change.actions[_] != "delete"
	lock_level := resource.change.after.lock_level
	lock_level != null
	msg := sprintf(
		"%s at %s sets lock_level %q. Management locks block terraform destroy.",
		[resource.type, resource.address, lock_level],
	)
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	resource.change.after.purge_protection_enabled == true
	msg := sprintf(
		"key vault at %s has purge_protection_enabled = true. Vault names stay reserved through soft-delete retention even after destroy.",
		[resource.address],
	)
}

deny contains msg if {
	resource := input.resource_changes[_]
	resource.type == "azurerm_key_vault"
	resource.change.actions[_] != "delete"
	resource.change.after.sku_name == "premium"
	env := resource.change.after.tags.environment
	env != "prod"
	msg := sprintf(
		"key vault at %s uses sku_name = premium in environment %q. Premium is allowed only in prod.",
		[resource.address, env],
	)
}
