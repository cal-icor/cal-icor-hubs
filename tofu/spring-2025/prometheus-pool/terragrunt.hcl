# Phase 1 (canary) of the public-to-private node migration: the private
# replacement for the existing public prometheus-pool-2025-12-22.
#
# Lowest-risk pool to move first — zero user impact (a metrics gap at worst), but
# stateful enough (the 1000Gi prometheus-data PD must reattach) to prove the full
# private path: Cloud NAT egress, Private Google Access, and PD reattachment.
#
# State key derives from this path: "spring-2025/prometheus-pool". The directory
# is role-named, not date-stamped, so it stays stable across future recreations;
# the date-stamped pool NAME lives in inputs below.
#
# Parity with the live prometheus-pool-2025-12-22 (describe 2026-06-28); the
# module defaults carry the shared config, so inputs here are only the
# prometheus-specific values plus the two migration deltas (private + name).

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../modules/nodepools"
}

inputs = {
  pool_name            = "prometheus-pool-2026-06-29"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "n2-standard-8"
  min_nodes    = 1
  max_nodes    = 3
  disk_size_gb = 100

  resource_labels = {
    hub                   = "prometheus"
    "nodepool-deployment" = "prometheus"
  }
}
