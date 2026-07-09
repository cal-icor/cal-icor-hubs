# Template, not a live unit. Copy tofu/cluster-template/ to tofu/<cluster-name>/
# and set the inputs. cluster_name is unset here on purpose, so a plan errors
# until you edit it.
#
# Same config for dev and prod; node VM size is set in the node-pool units.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/cluster"
}

inputs = {
  # Uncomment and set cluster_name, then pick ONE case block below.
  # cluster_name = "dev"

  # Dev cluster: own VPC, fresh non-colliding ranges; CI can tear it down.
  # create_network      = true
  # node_cidr_block     = "10.10.0.0/22"
  # pod_cidr_block      = "10.96.0.0/14"
  # resource_labels     = { hub = "dev" }
  # deletion_protection = false

  # Redeploy: reuse the live network and ranges so the NFS allowlist still matches.
  # create_network      = false
  # network             = "default"
  # node_cidr_block     = "10.7.196.0/22"
  # pod_cidr_block      = "10.92.0.0/14"
  # resource_labels     = { hub = "support" }
  # deletion_protection = true
}
