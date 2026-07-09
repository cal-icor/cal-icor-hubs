# support-pool: private pool for the shared cluster services (cert-manager,
# grafana, kube-state-metrics, the placeholder-scaler) and the in-cluster NFS
# server. Baseline mirrors spring-2025/support-pool; dev downsizes the
# machine_type.
#
# The NFS server and grafana carry zonal RWO PDs, so node_locations pins the one
# zone those disks live in.

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../../modules/nodepools"
}

dependency "cluster" {
  config_path = "../cluster"

  mock_outputs                            = { name = "mock-cluster" }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# NAT before private nodes, so egress works on first boot.
dependencies {
  paths = ["../network"]
}

inputs = {
  cluster              = dependency.cluster.outputs.name
  pool_name            = "support-pool" # house style: <role>-pool-YYYY-MM-DD
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "n2-standard-4" # dev: "n2-standard-2"
  min_nodes    = 1
  max_nodes    = 3
  disk_size_gb = 100

  resource_labels = {
    hub                   = "support"
    "nodepool-deployment" = "support"
  }
}
