output "name" {
  value       = google_container_cluster.cluster.name
  description = "Cluster name."
}

output "location" {
  value       = google_container_cluster.cluster.location
  description = "Cluster location (region or zone)."
}

output "endpoint" {
  value       = google_container_cluster.cluster.endpoint
  description = "Control-plane API endpoint."
}

output "cluster_ca_certificate" {
  value       = google_container_cluster.cluster.master_auth[0].cluster_ca_certificate
  description = "Base64 cluster CA certificate, for building a kubeconfig."
  sensitive   = true
}

output "self_link" {
  value       = google_container_cluster.cluster.self_link
  description = "Cluster self link."
}

output "network_name" {
  value       = local.network
  description = "VPC the cluster and its subnet live in. Feeds the network and node-pool units."
}

output "subnet_name" {
  value       = google_compute_subnetwork.cluster.name
  description = "Cluster subnet name."
}

output "node_cidr_block" {
  value       = google_compute_subnetwork.cluster.ip_cidr_range
  description = "Primary subnet range for node IPs. Feeds the NFS allowlist."
}

output "pod_cidr_block" {
  value       = google_compute_subnetwork.cluster.secondary_ip_range[0].ip_cidr_range
  description = "Subnet secondary range for pod IPs. Feeds the NFS allowlist."
}
