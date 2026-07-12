# user-pool: private pool for the student singleuser servers (and the
# placeholder-scaler's warm spares). Baseline mirrors spring-2025/user-pool; dev
# downsizes the machine_type.
#
# The only tainted pool: hub.jupyter.org_dedicated=user:NO_SCHEDULE, so only
# singleuser servers and placeholders land here. Scales to zero when idle.

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
  pool_name            = "user-pool" # house style: <role>-pool-YYYY-MM-DD
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type    = "n2-highmem-8" # dev: "n2-standard-4"
  min_nodes       = 0              # scales to zero; placeholder-scaler keeps one warm
  max_nodes       = 3
  location_policy = "ANY"
  disk_size_gb    = 200

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
