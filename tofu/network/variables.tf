variable "project" {
  type        = string
  default     = "cal-icor-hubs"
  description = "GCP project hosting the spring-2025 cluster."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for the Cloud Router, Cloud NAT, and egress IP."
}

variable "network" {
  type        = string
  default     = "default"
  description = "VPC network the spring-2025 cluster runs on."
}

variable "router_name" {
  type        = string
  default     = "spring-2025-nat-router"
  description = "Name of the Cloud Router that hosts the NAT config."
}

variable "nat_name" {
  type        = string
  default     = "spring-2025-nat"
  description = "Name of the Cloud NAT gateway."
}

variable "nat_egress_ip_name" {
  type        = string
  default     = "spring-2025-nat-egress"
  description = "Name of the reserved static egress IP used by Cloud NAT (outbound only)."
}

variable "iap_ssh_firewall_name" {
  type        = string
  default     = "spring-2025-allow-iap-ssh"
  description = "Name of the firewall rule allowing IAP-tunneled SSH to cluster nodes."
}

variable "iap_source_range" {
  type        = string
  default     = "35.235.240.0/20"
  description = "Google IAP TCP forwarding source range, for SSH to private nodes via --tunnel-through-iap."
}

variable "node_tag" {
  type        = string
  default     = "hub-cluster"
  description = "Network tag carried by every node pool in the spring-2025 cluster; firewall target for IAP SSH."
}
