# Phase 3 of the public-to-private node migration: the private replacement for
# the existing public support-pool-2026-02-12.
#
# The support pool runs the shared cluster services: cert-manager (+cainjector
# +webhook), kube-state-metrics, grafana, the statsd exporter, the
# node-placeholder-scaler, every hub's shared-dirsize-metrics reporter, and —
# the reason this phase is a MAINTENANCE WINDOW — the in-cluster NFS server
# (jupyterhub-home-nfs) that backs every hub's home directories.
#
# Two tenants carry RWO zonal PDs that must reattach on the move:
#   - jupyterhub-home-nfs  -> disk jupyterhub-homedirs-2026-04-08 (us-central1-b)
#   - support-grafana      -> its 10Gi standard PD            (us-central1-b)
# Both disks are zonal in us-central1-b, so this pool pins node_locations there
# (a zonal PD can't cross zones). During the NFS server's detach/reattach, home
# directories freeze cluster-wide for ~1-3 min (hard NFS mounts recover; not
# data loss) — hence the pre-login window.
#
# NOTE (operational, not expressible here): the home-nfs Deployment ships with
# strategy=RollingUpdate, NOT Recreate. With a RWO PD that deadlocks on a
# cross-pool move (the surged new pod can't attach the disk the old pod still
# holds -> Multi-Attach). The upstream chart does not expose a strategy override,
# so the cutover runbook handles it out of band (patch to Recreate / scale-to-0),
# the same PD-reattach mechanics proven on the prometheus canary. grafana and
# pushgateway are already strategy=Recreate, so they move cleanly.
#
# State key derives from this path: "spring-2025/support-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool
# NAME lives in inputs below.
#
# Parity with the live support-pool-2026-02-12 (describe 2026-07-06): the module
# defaults carry the shared config, so inputs here are only the support-specific
# values (machine_type n2-standard-4, support billing labels) plus the two
# migration deltas (private + date-stamped name). support sets no
# cpu_manager_policy and no node sysctls, so those module defaults are left as-is
# (unlike core); max_pods_per_node stays the module default 110 (matches live).

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
