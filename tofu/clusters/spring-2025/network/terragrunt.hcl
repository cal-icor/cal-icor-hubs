# Network unit for the spring-2025 cluster: Cloud Router, Cloud NAT, the reserved
# egress IP, and the IAP-SSH firewall rule.
#
# State key is derived from this path by the root config: "spring-2025/network",
# the same GCS prefix the module used before the Terragrunt conversion, so the
# existing applied state is reused. A plan here should report no changes.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/network"
}

locals {
  cluster = read_terragrunt_config(find_in_parent_folders("cluster.hcl")).locals
}

inputs = {
  network = local.cluster.network

  router_name           = "${local.cluster.cluster_name}-nat-router"
  nat_name              = "${local.cluster.cluster_name}-nat"
  nat_egress_ip_name    = "${local.cluster.cluster_name}-nat-egress"
  iap_ssh_firewall_name = "${local.cluster.cluster_name}-allow-iap-ssh"
}
