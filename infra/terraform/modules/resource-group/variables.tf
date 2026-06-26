variable "name" {
  description = "Name of the resource group."
  type        = string

  validation {
    condition     = length(var.name) >= 1 && length(var.name) <= 90
    error_message = "Resource group name must be between 1 and 90 characters."
  }
}

variable "location" {
  description = "Azure region for the resource group."
  type        = string
  default     = "spaincentral"
}

variable "environment" {
  description = "Environment the resource group belongs to, such as dev or prod."
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

variable "enable_delete_lock" {
  description = "Set true to add a CanNotDelete lock. Keep false so terraform destroy still works."
  type        = bool
  default     = false
}
