variable "bucket_name" {
  type        = string
  description = "Name of the GCS bucket holding OpenTofu remote state."
}

variable "location" {
  type        = string
  default     = "US-CENTRAL1"
  description = "Bucket location; same region as the cluster."
}

variable "labels" {
  type        = map(string)
  default     = { hub = "networking" }
  description = "Billing labels; 'networking' matches the network module's rollup."
}

variable "soft_delete_retention_seconds" {
  type        = number
  default     = 604800
  description = "Soft-delete retention window; 604800 = 7 days."
}
