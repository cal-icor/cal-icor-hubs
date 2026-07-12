# dev core-pool: the dev hub's hub + proxy pods and the ingress-nginx
# controller. Downsized from spring-2025/core-pool for a throwaway cluster.
#
# Kept at e2-standard-2 (8 GB), not smaller: ingress-nginx + one hub + its proxy
# sit on top of ~1.5 GB of GKE system daemons, so 4 GB would be too tight to
# guarantee the hub schedules.
#
# Other deviations from prod, by design for dev:
#   - no max_pods_per_node override: prod's 200 is for ~42 hubs; dev has one, so
#     the 110 cluster default is plenty.
#   - no cpu_manager_policy / DH-3 sysctls: those tune ingress-nginx under real
#     load; unnecessary on a dev cluster. See spring-2025/core-pool to add them.
#   - pool_name is role-only, not date-stamped: CI tears down and recreates this
#     cluster, so a frozen date would go stale on every rebuild.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/nodepools"
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs                            = { name = "mock-cluster", location = "us-central1-b" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# NAT before private nodes, so egress works on first boot.
dependencies {
  paths = ["../network"]
}

inputs = {
  cluster              = dependency.cluster.outputs.name
  location             = dependency.cluster.outputs.location
  pool_name            = "core-pool"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "e2-standard-2"
  min_nodes    = 1
  max_nodes    = 2
  disk_size_gb = 50

  resource_labels = {
    hub                   = "core"
    "nodepool-deployment" = "core"
  }
}
