locals {
  default_tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }

  tags = merge(local.default_tags, var.tags)
}

resource "azurerm_resource_group" "this" {
  name     = var.name
  location = var.location
  tags     = local.tags
}

resource "azurerm_management_lock" "this" {
  count = var.enable_delete_lock ? 1 : 0

  name       = "${var.name}-no-delete"
  scope      = azurerm_resource_group.this.id
  lock_level = "CanNotDelete"
  notes      = "Prevents accidental deletion. Off by default so terraform destroy works."
}
