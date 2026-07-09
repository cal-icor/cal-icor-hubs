# prometheus-pool: private pool for prometheus-server (stateful; its data PD
# reattaches). Baseline mirrors spring-2025/prometheus-pool; dev downsizes the
# machine_type.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/nodepools"
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs                            = { name = "mock-cluster" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# NAT before private nodes, so egress works on first boot.
dependencies {
  paths = ["../network"]
}

inputs = {
  cluster              = dependency.cluster.outputs.name
  pool_name            = "prometheus-pool" # house style: <role>-pool-YYYY-MM-DD
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "n2-standard-8" # dev: "n2-standard-2"
  min_nodes    = 1
  max_nodes    = 3
  disk_size_gb = 100

  resource_labels = {
    hub                   = "prometheus"
    "nodepool-deployment" = "prometheus"
  }
}
