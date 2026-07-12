# core-pool: private pool for every hub's hub/proxy pods and the shared
# ingress-nginx controller. Baseline mirrors spring-2025/core-pool; dev
# downsizes the machine_type.
#
# In prod the core pool also carries cpu_manager_policy = "static" and the DH-3
# TCP sysctls (net.core.* / net.ipv4.tcp_*). Both are immutable-at-creation
# tuning; see spring-2025/core-pool for the full block. Add them here if this
# cluster must match prod exactly.

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
  pool_name            = "core-pool" # house style: <role>-pool-YYYY-MM-DD
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type      = "n2-standard-8" # dev: "n2-standard-4"
  min_nodes         = 1
  max_nodes         = 3
  disk_size_gb      = 100
  max_pods_per_node = 200 # each hub runs 2 hub + 2 proxy pods; density-bound

  resource_labels = {
    hub                   = "core"
    "nodepool-deployment" = "core"
  }
}
