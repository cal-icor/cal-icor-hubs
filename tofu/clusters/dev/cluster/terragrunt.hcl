# dev: throwaway GKE cluster for the keyless end-to-end deploy pilot. Its own
# VPC and fresh ranges, so nothing here can collide with prod's default network;
# deletion_protection off so CI can tear it down and rebuild.
#
# Zonal (location = a zone, not the region), single zone us-central1-b, to match
# where the dev NFS/home-dirs PDs live and to keep the throwaway cluster cheap
# (one control plane, not three). Node VM sizes are set per pool, downsized.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/cluster"
}

inputs = {
  cluster_name = "dev"

  # Zonal, not regional: a zone here gives a single-zone cluster in us-central1-b.
  location = "us-central1-b"

  # Empty overrides the module default ["us-central1-b"] (written for the regional
  # prod cluster). For a zonal cluster, node_locations must NOT list its own zone,
  # so nodes just land in the cluster's zone. Pool-level node_locations still pin
  # each pool to us-central1-b (google_container_node_pool, different semantics).
  node_locations = []

  # Own VPC, fresh non-colliding ranges; CI can tear it down.
  create_network      = true
  node_cidr_block     = "10.10.0.0/22"
  pod_cidr_block      = "10.96.0.0/14"
  resource_labels     = { hub = "dev" }
  deletion_protection = false
}
