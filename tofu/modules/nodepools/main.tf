# Reusable module for rebuilding a spring-2025 node pool as a PRIVATE pool (nodes
# get internal IPs only; egress flows through the Cloud NAT in modules/network).
#
# The migration is build-alongside: create a new private pool with this module,
# drain the old public pool onto it, then delete the old pool. So this module
# only ever CREATES a pool; it never mutates the existing public pools (which are
# not tofu-managed). Config mirrors the pool being replaced exactly, changed only
# by two deltas the caller sets: enable_private_nodes = true and a date-stamped
# name.

resource "google_container_node_pool" "pool" {
  name     = var.pool_name
  cluster  = var.cluster
  location = var.region # regional cluster: the pool's location is the region

  # Pin the actual node zone(s). Single zone for spring-2025 so stateful pods can
  # reattach their zonal PDs.
  node_locations = var.node_locations

  # Matches how the existing pools were created (1 node per zone); the autoscaler
  # takes over from there.
  initial_node_count = var.initial_node_count

  autoscaling {
    min_node_count  = var.min_nodes
    max_node_count  = var.max_nodes
    location_policy = var.location_policy
  }

  max_pods_per_node = var.max_pods_per_node

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  # The migration delta. Per-pool because the cluster itself is not flipped to
  # private; each new pool opts in as it is created.
  network_config {
    enable_private_nodes = var.enable_private_nodes
  }

  node_config {
    machine_type = var.machine_type
    image_type   = var.image_type
    disk_type    = var.disk_type
    disk_size_gb = var.disk_size_gb

    service_account = var.node_service_account
    oauth_scopes    = var.oauth_scopes

    tags = var.node_tags

    # Kubernetes node labels. hub.jupyter.org/pool-name is the label helm
    # nodeSelectors pin, so it must equal the pool name; callers can merge in
    # anything else they need.
    labels = merge(
      { "hub.jupyter.org/pool-name" = var.pool_name },
      var.extra_node_labels,
    )

    # GCE instance labels — the billing/rollup dimension, keyed on hub.
    resource_labels = var.resource_labels

    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_integrity_monitoring = true
    }

    kubelet_config {
      insecure_kubelet_readonly_port_enabled = var.insecure_kubelet_readonly_port_enabled
      # Omitted when null (prometheus); "static" on the core pool for parity.
      cpu_manager_policy = var.cpu_manager_policy
    }

    # Kernel sysctl tuning. Emitted only when sysctls are passed (the core pool's
    # DH-3 TCP/IP tuning); omitted for pools that pass none, so they keep GKE
    # node defaults and stay a no-op.
    dynamic "linux_node_config" {
      for_each = length(var.linux_node_sysctls) > 0 ? [1] : []
      content {
        sysctls = var.linux_node_sysctls
      }
    }

    dynamic "taint" {
      for_each = var.node_taints
      content {
        key    = taint.value.key
        value  = taint.value.value
        effect = taint.value.effect
      }
    }
  }

  # GKE rewrites node_count as the autoscaler runs; ignore it so applies don't
  # fight the autoscaler.
  lifecycle {
    ignore_changes = [node_count]
  }
}
