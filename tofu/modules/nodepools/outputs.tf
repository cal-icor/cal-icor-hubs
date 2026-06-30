output "pool_name" {
  value       = google_container_node_pool.pool.name
  description = "Name of the created node pool."
}

output "pool_id" {
  value       = google_container_node_pool.pool.id
  description = "Fully qualified GKE node pool ID."
}

output "pool_name_selector" {
  value       = "hub.jupyter.org/pool-name=${google_container_node_pool.pool.name}"
  description = "The node label helm nodeSelectors must pin to schedule onto this pool. Use it when updating the paired helm config before draining the old pool."
}
