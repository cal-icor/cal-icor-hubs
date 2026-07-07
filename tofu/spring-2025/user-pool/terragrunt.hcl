# Phase 4 of the public-to-private node migration: the private replacement for
# the existing public user-base pool. This is the final phase.
#
# The user pool runs the student singleuser notebook servers (and the
# node-placeholder-scaler's warm-spare placeholders). It is the only pool with a
# taint: hub.jupyter.org_dedicated=user:NO_SCHEDULE, so only pods that tolerate
# it (singleuser servers + placeholders) land here. Scheduling is by the
# hub.jupyter.org/pool-name node label, which the module sets to the pool name.
#
# GRACEFUL cutover (no maintenance window, no forced kills): draining this pool
# would kill live student sessions, so the old pool is not drained. Instead the
# new pool is created, the singleuser + placeholder nodeSelectors are repointed
# to user-pool-2026-07-07 (paired helm PR), new spawns land here, and the old
# user-base pool is cordoned and left to empty out via the culler (idle 30m /
# maxAge 12h) before it is deleted.
#
# State key derives from this path: "spring-2025/user-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool
# NAME lives in inputs below.
#
# Parity with the live user-base pool (describe 2026-07-07): the module defaults
# carry the shared config, so inputs here are only the user-specific values plus
# the two migration deltas (private + date-stamped name). Differences from the
# other pools that this unit sets explicitly:
#   - machine_type n2-highmem-8 (students are memory-bound)
#   - disk_size_gb 200 (the other pools use 100)
#   - min_nodes 0 (the pool scales to zero when idle; the placeholder-scaler
#     keeps a node warm in practice)
#   - location_policy ANY (user-base uses ANY; the other pools use BALANCED)
#   - node_taints hub.jupyter.org_dedicated=user:NO_SCHEDULE
#   - resource_labels hub=base (billing parity with the live pool)
# No cpu_manager_policy and no node sysctls, so those module defaults are left
# as-is (unlike core); max_pods_per_node stays the module default 110 (matches
# live).

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../modules/nodepools"
}

inputs = {
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
