variable "name" {
  description = "Name of the Key Vault. Must be globally unique across Azure."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]$", var.name))
    error_message = "Key Vault name must be 3 to 24 characters, start with a letter, end with a letter or digit, and contain only letters, digits, and hyphens."
  }
}

variable "resource_group_name" {
  description = "Name of the resource group that holds the Key Vault."
  type        = string
}

variable "location" {
  description = "Azure region for the Key Vault."
  type        = string
  default     = "spaincentral"
}

variable "tenant_id" {
  description = "Azure AD tenant ID the Key Vault belongs to."
  type        = string
}

variable "environment" {
  description = "Environment the Key Vault belongs to, such as dev or prod."
  type        = string
}

variable "project" {
  description = "Project name used for tagging."
  type        = string
  default     = "theft-detection"
}

variable "tags" {
  description = "Extra tags merged on top of the module defaults."
  type        = map(string)
  default     = {}
}

variable "sku_name" {
  description = "Key Vault SKU. Use standard for dev, premium only when HSM-backed keys are required."
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["standard", "premium"], var.sku_name)
    error_message = "sku_name must be standard or premium."
  }
}

variable "soft_delete_retention_days" {
  description = "Days to retain soft-deleted vault contents. 7 keeps cost low and lets you purge faster between destroy and recreate in dev."
  type        = number
  default     = 7

  validation {
    condition     = var.soft_delete_retention_days >= 7 && var.soft_delete_retention_days <= 90
    error_message = "soft_delete_retention_days must be between 7 and 90."
  }
}

variable "purge_protection_enabled" {
  description = "When true, the vault cannot be purged until soft-delete retention expires. Keep false in dev so terraform destroy works."
  type        = bool
  default     = false
}

variable "enable_rbac_authorization" {
  description = "Use Azure RBAC for data plane access instead of legacy access policies."
  type        = bool
  default     = true
}

variable "public_network_access_enabled" {
  description = "When true, the vault accepts traffic from the public internet subject to network ACLs. Default false ships the vault closed."
  type        = bool
  default     = false
}

variable "network_acls_default_action" {
  description = "Default action when no network ACL rule matches. Allow or Deny."
  type        = string
  default     = "Deny"

  validation {
    condition     = contains(["Allow", "Deny"], var.network_acls_default_action)
    error_message = "network_acls_default_action must be Allow or Deny."
  }
}

variable "network_acls_bypass" {
  description = "Traffic categories that bypass network ACLs. AzureServices or None."
  type        = string
  default     = "AzureServices"

  validation {
    condition     = contains(["AzureServices", "None"], var.network_acls_bypass)
    error_message = "network_acls_bypass must be AzureServices or None."
  }
}

variable "network_acls_ip_rules" {
  description = "IP CIDR ranges allowed to reach the vault."
  type        = list(string)
  default     = []
}

variable "network_acls_virtual_network_subnet_ids" {
  description = "Subnet IDs allowed to reach the vault. Wire from the networking module outputs."
  type        = list(string)
  default     = []
}
