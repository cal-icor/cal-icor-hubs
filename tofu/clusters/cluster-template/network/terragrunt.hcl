# Network unit: Cloud Router, Cloud NAT, reserved egress IP, and the IAP-SSH
# firewall for this cluster. Private node pools egress through the NAT.
#
# Depends on cluster/ for the VPC and to derive resource names, so the NAT and
# firewall never collide with another cluster's (e.g. spring-2025-*).

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/network"
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs = {
    name         = "mock-cluster"
    network_name = "mock-network"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  network = dependency.cluster.outputs.network_name

  router_name           = "${dependency.cluster.outputs.name}-nat-router"
  nat_name              = "${dependency.cluster.outputs.name}-nat"
  nat_egress_ip_name    = "${dependency.cluster.outputs.name}-nat-egress"
  iap_ssh_firewall_name = "${dependency.cluster.outputs.name}-allow-iap-ssh"
}
