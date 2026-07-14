# dev user-pool: the single dev user's singleuser server. Downsized from
# spring-2025/user-pool for a throwaway cluster with exactly one user.
#
# The only tainted pool: hub.jupyter.org_dedicated=user:NO_SCHEDULE, so only
# singleuser servers land here. Scales to zero when idle.
#
# Deviations from prod, by design for dev:
#   - machine_type e2-medium (4 GB): one dev user, one small singleuser pod. The
#     dev hub's mem_guarantee is set small to match; bump this if it OOMs.
#   - max_nodes 1: one user means at most one user pod, so one node.
#   - pool_name role-only, not date-stamped (CI recreates the cluster).

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
  pool_name            = "user-pool"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type    = "e2-medium"
  min_nodes       = 1 # so we always have a node for the single dev user
  max_nodes       = 1
  location_policy = "ANY"
  disk_size_gb    = 50

  resource_labels = {
    hub                   = "base"
    "nodepool-deployment" = "base"
  }

  node_taints = [
    {
      key    = "hub.jupyter.org_dedicated"
      value  = "user"
      effect = "NO_SCHEDULE"
    },
  ]
}
