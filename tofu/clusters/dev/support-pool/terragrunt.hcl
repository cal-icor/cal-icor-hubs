# dev support-pool: the shared cluster services (cert-manager, grafana,
# kube-state-metrics, the placeholder-scaler) and the in-cluster NFS server.
# Downsized from spring-2025/support-pool for a throwaway cluster.
#
# Kept at e2-standard-2 (8 GB), the one pool not shrunk to 4 GB: it carries the
# most pods (NFS server + several system services) on top of the GKE daemons, so
# it gets the safety margin.
#
# The NFS server and grafana carry zonal RWO PDs, so node_locations pins the one
# zone those disks live in (the dev NFS/home-dirs disk is in us-central1-b).
#
# pool_name role-only, not date-stamped (CI recreates the cluster).

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/nodepools"
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs                            = { name = "mock-cluster", location = "us-central1-b" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# NAT before private nodes, so egress works on first boot.
dependencies {
  paths = ["../network"]
}

inputs = {
  cluster              = dependency.cluster.outputs.name
  location             = dependency.cluster.outputs.location
  pool_name            = "support-pool"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "e2-standard-2"
  min_nodes    = 1
  max_nodes    = 2
  disk_size_gb = 50

  resource_labels = {
    hub                   = "support"
    "nodepool-deployment" = "support"
  }
}
