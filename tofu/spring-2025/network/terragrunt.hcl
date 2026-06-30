# Network unit for the spring-2025 cluster: Cloud Router, Cloud NAT, the reserved
# egress IP, and the IAP-SSH firewall rule (Phases A and 0 of the public-to-
# private node migration).
#
# State key is derived from this path by the root config: "spring-2025/network" —
# the same GCS prefix the module used before the Terragrunt conversion, so the
# existing applied state is reused. A plan here should report no changes.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../modules/network"
}
