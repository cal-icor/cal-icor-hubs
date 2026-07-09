# A second user pool, dedicated to workshops. Unlike the always-on user pool
# (which runs the regular student singleuser servers), this pool is normally
# scaled to zero and costs nothing. It is spun up only when a workshop is
# scheduled, then scaled back to zero afterward.
#
# Sizing (workshop = ~20-50 concurrent users, each 2G guarantee == limit, so no
# overcommit is possible and a full 100G of ALLOCATABLE memory is needed):
#   - machine_type n2d-highmem-16 (16 vCPU / 128G). After GKE system + daemonset
#     reservations a 128G node leaves ~116G allocatable, enough for all 50 users
#     at 2G on ONE node with headroom. An n2-highmem-8 (64G) only fits ~28, which
#     would split a 50-person cohort across two nodes. n2d (AMD) is ~10-11%
#     cheaper than n2 for identical specs; raw n2 pricing is linear so one
#     highmem-16 costs the same as two highmem-8s, but the single bigger node
#     wastes less to per-node overhead and keeps the cohort together.
#   - initial_node_count 0 and min_nodes 0: the pool is created empty. Scale it
#     up (set max_nodes reached by the autoscaler as pods schedule, or bump
#     min_nodes for the duration of a workshop) only when a workshop runs.
#   - max_nodes 2: a safety valve for a 50+ turnout or a straggler pod that can't
#     fit the first node. The second node only spins up if the first is full.
#
# Tainted hub.jupyter.org_dedicated=user:NO_SCHEDULE, the SAME value as the
# regular user pool. z2jh gives every singleuser pod a default toleration for
# this taint (scheduling.userPods.tolerations), so routing a workshop onto this
# pool needs only a nodeSelector change (hub.jupyter.org/pool-name =
# workshop-pool-2026-07-07) in the hub's singleuser config, no extra toleration.
# The taint's job is only to keep non-tolerating system pods off this pricey
# highmem node. Which user pods land here vs. the shared student pool is decided
# entirely by the nodeSelector, so keep those set deliberately per hub.
#
# Private + Cloud NAT egress like every other pool post-migration.
#
# State key derives from this path: "spring-2025/workshop-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool
# NAME lives in inputs below.
#
# Billing: resource_labels hub=workshop so this pool's node cost rolls up as a
# distinct line, separate from the shared student pool's hub=base.

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

  pool_name            = "workshop-pool-2026-07-07"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type       = "n2d-highmem-16"
  initial_node_count = 0
  min_nodes          = 0
  max_nodes          = 2
  location_policy    = "ANY"
  disk_size_gb       = 200

  resource_labels = {
    hub                   = "workshop"
    "nodepool-deployment" = "workshop"
  }

  node_taints = [
    {
      key    = "hub.jupyter.org_dedicated"
      value  = "user"
      effect = "NO_SCHEDULE"
    },
  ]
}
