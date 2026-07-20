# Private node pool for the student singleuser notebook servers (and the
# node-placeholder-scaler's warm-spare placeholders). It is the only pool with a
# taint: hub.jupyter.org_dedicated=user:NO_SCHEDULE, so only pods that tolerate
# it (singleuser servers + placeholders) land here. Scheduling is by the
# hub.jupyter.org/pool-name node label, which the module sets to the pool name.
#
# State key derives from this path: "spring-2025/user-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool NAME
# lives in inputs below.
#
# The module defaults carry the shared config; inputs here are the user-specific
# values this unit sets explicitly:
#   - machine_type n2-highmem-8 (students are memory-bound)
#   - disk_size_gb 200 (the other pools use 100)
#   - min_nodes 0 (scales to zero when idle; the placeholder-scaler keeps a node
#     warm in practice)
#   - location_policy ANY (the other pools use BALANCED)
#   - node_taints hub.jupyter.org_dedicated=user:NO_SCHEDULE
#   - resource_labels hub=base (billing rollup)
# No cpu_manager_policy and no node sysctls; max_pods_per_node stays the module
# default 110.

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

  pool_name            = "user-pool-2026-07-07"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type    = "n2-highmem-8"
  min_nodes       = 0
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
