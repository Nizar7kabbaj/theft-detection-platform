variable "name" {
  description = "Name of the virtual network."
  type        = string

  validation {
    condition     = length(var.name) >= 2 && length(var.name) <= 64
    error_message = "VNet name must be between 2 and 64 characters."
  }
}

variable "resource_group_name" {
  description = "Name of the resource group the VNet lives in."
  type        = string
}

variable "location" {
  description = "Azure region for the VNet and its child resources."
  type        = string
  default     = "spaincentral"
}

variable "environment" {
  description = "Deployment environment (dev, prod, etc.). Used in default tags."
  type        = string
}

variable "project" {
  description = "Project name. Used in default tags."
  type        = string
  default     = "theft-detection"
}

variable "address_space" {
  description = "Address space for the VNet, as a list of CIDR blocks."
  type        = list(string)

  validation {
    condition     = length(var.address_space) > 0
    error_message = "address_space must contain at least one CIDR block."
  }
}

variable "subnets" {
  description = <<-EOT
    Map of subnets to create inside the VNet. Key is the subnet name.

    Each subnet supports:
      address_prefixes                  - list of CIDR blocks (required)
      service_endpoints                 - list of service endpoints (optional, default [])
      private_endpoint_network_policies - "Enabled" or "Disabled" (optional, default "Enabled")
      delegation                        - optional service delegation block
      create_nsg                        - whether the module creates an NSG for this subnet (optional, default true)
      security_rules                    - list of NSG rules attached to this subnet's NSG (optional, default [])
  EOT

  type = map(object({
    address_prefixes                  = list(string)
    service_endpoints                 = optional(list(string), [])
    private_endpoint_network_policies = optional(string, "Enabled")
    delegation = optional(object({
      name         = string
      service_name = string
      actions      = list(string)
    }))
    create_nsg = optional(bool, true)
    security_rules = optional(list(object({
      name                         = string
      priority                     = number
      direction                    = string
      access                       = string
      protocol                     = string
      source_port_range            = optional(string)
      source_port_ranges           = optional(list(string))
      destination_port_range       = optional(string)
      destination_port_ranges      = optional(list(string))
      source_address_prefix        = optional(string)
      source_address_prefixes      = optional(list(string))
      destination_address_prefix   = optional(string)
      destination_address_prefixes = optional(list(string))
    })), [])
  }))

  default = {}
  validation {
    condition = alltrue([
      for subnet_name, subnet in var.subnets :
      length(subnet.security_rules) == length(distinct([for rule in subnet.security_rules : rule.priority]))
    ])
    error_message = "Each subnet's security_rules must have unique priorities."
  }
}

variable "private_dns_zones" {
  description = "List of private DNS zone names to create and link to this VNet (e.g. privatelink.blob.core.windows.net)."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional tags merged on top of the module's default tags. Caller-provided keys override defaults on collision."
  type        = map(string)
  default     = {}
}
