variable "cluster_name" {
  type        = string
  description = "GKE cluster name. Also the unit directory under tofu/."
}

variable "location" {
  type        = string
  default     = "us-central1"
  description = "Cluster location. A region gives a regional cluster."
}

variable "node_locations" {
  type        = list(string)
  default     = ["us-central1-b"]
  description = "Zones the cluster places nodes in."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for the cluster's subnet."
}

variable "create_network" {
  type        = bool
  default     = false
  description = "Create a dedicated VPC named cluster_name (own-VPC-per-cluster). False attaches the subnet to the existing var.network."
}

variable "network" {
  type        = string
  default     = "default"
  description = "Existing VPC for the cluster and its subnet when create_network is false. Ignored when create_network is true."
}

variable "subnet_name" {
  type        = string
  default     = null
  description = "Subnet name. Null derives it from cluster_name."
}

variable "node_cidr_block" {
  type        = string
  description = "Primary subnet range for node IPs."
}

variable "pod_cidr_block" {
  type        = string
  description = "Subnet secondary range for pod IPs."
}

variable "max_pods_per_node" {
  type        = number
  default     = 110
  description = "Default max pods per node."
}

variable "release_channel" {
  type        = string
  default     = "REGULAR"
  description = "GKE release channel."

  validation {
    condition     = contains(["RAPID", "REGULAR", "STABLE"], var.release_channel)
    error_message = "Must be RAPID, REGULAR, or STABLE."
  }
}

variable "resource_labels" {
  type        = map(string)
  default     = {}
  description = "GCE resource labels on the cluster (billing/rollup)."
}

variable "deletion_protection" {
  type        = bool
  default     = true
  description = "Blocks tofu from deleting the cluster. Set false for clusters CI/CD tears down."
}
