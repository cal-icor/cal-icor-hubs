variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region of the regional spring-2025 cluster; also the node pool's location. Value comes from root.hcl inputs."
}

variable "cluster" {
  type        = string
  default     = "spring-2025"
  description = "Name of the GKE cluster this node pool belongs to."
}

variable "pool_name" {
  type        = string
  description = "Node pool name. House style is <role>-pool-YYYY-MM-DD, stamped with the day the pool is created. Also used as the value of the hub.jupyter.org/pool-name node label that helm nodeSelectors pin."
}

variable "node_locations" {
  type        = list(string)
  default     = ["us-central1-b"]
  description = "Zones the pool places nodes in. Must be a single zone matching any attached zonal PD (prometheus-data and the NFS disk are both in us-central1-b) so stateful pods can reattach."
}

variable "enable_private_nodes" {
  type        = bool
  default     = true
  description = "Whether nodes get internal IPs only (no external IP). True is the point of the migration; egress then flows through the Cloud NAT in modules/network. Set per-pool because the cluster-level flag is off."
}

variable "machine_type" {
  type        = string
  description = "Compute machine type for the pool's nodes (e.g. n2-standard-8)."
}

variable "initial_node_count" {
  type        = number
  default     = 1
  description = "Number of nodes created per zone when the pool is first created. The existing pools were created with 1."
}

variable "min_nodes" {
  type        = number
  description = "Autoscaler minimum node count."
}

variable "max_nodes" {
  type        = number
  description = "Autoscaler maximum node count."
}

variable "location_policy" {
  type        = string
  default     = "BALANCED"
  description = "Autoscaler location policy. BALANCED matches the existing pools."
}

variable "disk_size_gb" {
  type        = number
  default     = 100
  description = "Boot disk size in GB."
}

variable "disk_type" {
  type        = string
  default     = "pd-balanced"
  description = "Boot disk type."
}

variable "image_type" {
  type        = string
  default     = "COS_CONTAINERD"
  description = "Node image type."
}

variable "max_pods_per_node" {
  type        = number
  default     = 110
  description = "Maximum pods schedulable per node."
}

variable "node_service_account" {
  type        = string
  default     = "default"
  description = "Service account for the nodes. The existing pools use the default compute SA."
}

variable "oauth_scopes" {
  type = list(string)
  default = [
    "https://www.googleapis.com/auth/devstorage.read_only",
    "https://www.googleapis.com/auth/logging.write",
    "https://www.googleapis.com/auth/monitoring",
    "https://www.googleapis.com/auth/service.management.readonly",
    "https://www.googleapis.com/auth/servicecontrol",
    "https://www.googleapis.com/auth/trace.append",
  ]
  description = "OAuth scopes for the node service account. Defaults to the six GKE default scopes carried by the existing pools."
}

variable "node_tags" {
  type        = list(string)
  default     = ["hub-cluster"]
  description = "Network tags on the nodes. hub-cluster is the custom cluster-wide tag the firewall rules (including the IAP-SSH rule) target."
}

variable "resource_labels" {
  type        = map(string)
  description = "GCE instance labels applied to the nodes (billing/rollup dimension). The repo keys billing on hub; e.g. { hub = \"prometheus\", nodepool-deployment = \"prometheus\" }."
}

variable "extra_node_labels" {
  type        = map(string)
  default     = {}
  description = "Additional Kubernetes node labels merged in alongside the always-set hub.jupyter.org/pool-name label."
}

variable "node_taints" {
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  default     = []
  description = "Kubernetes node taints. Empty for nodeSelector-scheduled pools (prometheus/core/support); the user pool sets hub.jupyter.org_dedicated=user:NO_SCHEDULE."
}

variable "insecure_kubelet_readonly_port_enabled" {
  # The google provider types this as a string enum, not a bool.
  type        = string
  default     = "FALSE"
  description = "Whether the unauthenticated kubelet read-only port (10255) is open, as the string \"TRUE\" or \"FALSE\". The existing pools have it disabled; keep \"FALSE\"."

  validation {
    condition     = contains(["TRUE", "FALSE"], var.insecure_kubelet_readonly_port_enabled)
    error_message = "Must be the string \"TRUE\" or \"FALSE\"."
  }
}

variable "cpu_manager_policy" {
  # Null (the default) omits the field, leaving the GKE default of "none" — that
  # matches prometheus-pool. The core pool was created with "static", so its
  # replacement unit sets it explicitly to preserve 1:1 parity. The setting is
  # immutable on a live pool, so it must be chosen at creation; today it is a
  # no-op on core (no Guaranteed-QoS integer-CPU pods land there) but is kept to
  # avoid any behavioral change during the migration.
  type        = string
  default     = null
  description = "kubelet CPU manager policy: \"static\" pins whole cores to Guaranteed-QoS integer-CPU pods; null/\"none\" shares all cores. Set \"static\" for the core pool to match the pool it replaces."

  validation {
    condition     = var.cpu_manager_policy == null ? true : contains(["static", "none"], var.cpu_manager_policy)
    error_message = "Must be null, \"static\", or \"none\"."
  }
}

variable "linux_node_sysctls" {
  # An empty map (the default) omits linux_node_config entirely, leaving GKE
  # node defaults — that matches prometheus-pool. The core pool carries the DH-3
  # TCP/IP stack tuning (net.core.* / net.ipv4.tcp_*), set inline in its unit.
  type        = map(string)
  default     = {}
  description = "Kernel sysctls applied to the nodes via linux_node_config. Empty omits the block; the core pool passes its TCP/IP tuning values."
}
