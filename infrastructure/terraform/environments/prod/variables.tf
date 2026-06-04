variable "environment" {
  description = "Deployment environment name. Pinned to prod for this root."
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod"], var.environment)
    error_message = "environment must be prod for this root."
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
  validation {
    condition     = contains(["spaincentral"], var.location)
    error_message = "location must be spaincentral. Azure for Students blocks Microsoft.Storage in francecentral (see lesson #98)."
  }
}

variable "owner" {
  description = "Owner tag value. Identifies the human responsible for the environment."
  type        = string
  default     = "nizar"
}
