# dev prometheus-pool: prometheus-server (stateful; its data PD reattaches).
# Downsized from spring-2025/prometheus-pool for a throwaway cluster.
#
# machine_type e2-medium (4 GB): the dev cluster scrapes a handful of nodes and
# one hub, so series cardinality is tiny. This is the pool most likely to need a
# bump if prometheus OOMs on first spin-up; the fix is one line here to
# e2-standard-2.
#
# pool_name role-only, not date-stamped (CI recreates the cluster).

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
  pool_name            = "prometheus-pool"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "e2-medium"
  min_nodes    = 1
  max_nodes    = 2
  disk_size_gb = 50

  resource_labels = {
    hub                   = "prometheus"
    "nodepool-deployment" = "prometheus"
  }
}
