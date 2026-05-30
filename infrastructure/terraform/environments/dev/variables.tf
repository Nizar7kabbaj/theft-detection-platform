variable "environment" {
  description = "Deployment environment name. Used in resource names and tags."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "project" {
  description = "Project name. Used in resource names and tags."
  type        = string
  default     = "theft-detection"
}

variable "location" {
  description = "Azure region for all resources in this environment."
  type        = string
  default     = "spaincentral"
}

variable "owner" {
  description = "Owner tag value. Identifies the human responsible for the environment."
  type        = string
  default     = "nizar"
}