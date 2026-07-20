# Private node pool for the shared cluster services: cert-manager (+cainjector
# +webhook), kube-state-metrics, grafana, the statsd exporter, the
# node-placeholder-scaler, every hub's shared-dirsize-metrics reporter, and the
# in-cluster NFS server (jupyterhub-home-nfs) that backs every hub's home
# directories.
#
# Two tenants carry RWO zonal PDs, both in us-central1-b, so this pool pins
# node_locations there (a zonal PD cannot cross zones):
#   - jupyterhub-home-nfs -> disk jupyterhub-homedirs-2026-04-08
#   - support-grafana     -> its 10Gi standard PD
#
# NOTE (operational, not expressible here): the home-nfs Deployment ships with
# strategy=RollingUpdate, not Recreate. With a RWO PD that deadlocks on any move:
# the surged new pod cannot attach the disk the old pod still holds (Multi-Attach).
# The upstream chart exposes no strategy override, so a move of this pod is handled
# out of band (patch to Recreate / scale to 0) before it reschedules. grafana and
# pushgateway are already strategy=Recreate, so they move cleanly.
#
# State key derives from this path: "spring-2025/support-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool NAME
# lives in inputs below.
#
# The module defaults carry the shared config; inputs here are only the
# support-specific values (machine_type n2-standard-4, billing labels). support
# sets no cpu_manager_policy and no node sysctls, and max_pods_per_node stays the
# module default 110.

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

  pool_name            = "support-pool-2026-07-07"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type = "n2-standard-4"
  min_nodes    = 1
  max_nodes    = 3
  disk_size_gb = 100

  resource_labels = {
    hub                   = "support"
    "nodepool-deployment" = "support"
  }
}
