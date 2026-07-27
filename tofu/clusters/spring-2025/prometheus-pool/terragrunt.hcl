# Private node pool for prometheus-server. It carries the 1000Gi prometheus-data
# PD, which is zonal in us-central1-b, so node_locations pins that zone so the
# stateful pod can reattach its disk.
#
# State key derives from this path: "spring-2025/prometheus-pool". The directory
# is role-named, not date-stamped, so it stays stable across recreations; the
# date-stamped pool NAME lives in inputs below.
#
# The module defaults carry the shared config; inputs here are only the
# prometheus-specific values.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/nodepools"
}

locals {
  cluster = read_terragrunt_config(find_in_parent_folders("cluster.hcl")).locals
}

inputs = {
  cluster = local.cluster.cluster_name

  pool_name            = "prometheus-pool-2026-06-29"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "n2-standard-4"
  min_nodes    = 1
  max_nodes    = 3
  disk_size_gb = 100

  resource_labels = {
    hub                   = "prometheus"
    "nodepool-deployment" = "prometheus"
  }
}
