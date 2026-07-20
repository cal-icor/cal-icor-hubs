# Private node pool for every hub's hub + proxy pods plus the shared
# support-ingress-nginx controller (the single public ingress fronting all hubs).
# These are stateless Deployments with no attached PDs.
#
# State key derives from this path: "spring-2025/core-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool NAME
# lives in inputs below.
#
# machine_type n2-standard-8 (8 vCPU / 32 GB, ~28 GiB allocatable). The workload
# (every hub's hub + proxy pods + the 3 ingress replicas + GKE system daemons) is
# memory-shaped and light on CPU: measured 2026-07-06, 104 pods requesting 2600m
# CPU (35%) / 15.6 GiB mem (27%), real usage 761m CPU (10%) / 11.6 GiB (19%). The
# 32 GB holds the 15.6 GiB of requests at ~55% with room for ~19 more hub pairs,
# and the 8 vCPU is headroom for a full-fleet redeploy (all ~42 hub+proxy pods
# restarting at once). The 16 GB n2 tiers were ruled out: their ~13 GiB
# allocatable is below the 15.6 GiB of requests, so pods would not schedule.
#
# max_pods_per_node = 200 for high pod density (each hub runs 2 hub + 2 proxy
# pods, so pod count, not CPU/RAM, is the binding limit). cpu_manager_policy =
# "static", immutable on a live pool so it is set at creation.

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

  pool_name            = "core-pool-2026-06-30"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type      = "n2-standard-8"
  min_nodes         = 1
  max_nodes         = 3
  disk_size_gb      = 100
  max_pods_per_node = 200

  # cpu_manager_policy and the sysctls below are set here in tofu rather than out
  # of band. cpu_manager_policy is immutable on a live pool, so it is set at
  # creation.
  cpu_manager_policy = "static"

  # DH-3 TCP/IP stack tuning, so ingress-nginx doesn't exhaust TCP memory under
  # load on the shared core node. Ref: https://jira-secure.berkeley.edu/browse/DH-3
  # Process: https://cloud.google.com/kubernetes-engine/docs/how-to/node-system-config
  # tcp(7): https://man7.org/linux/man-pages/man7/tcp.7.html
  # Sources: https://fasterdata.es.net/host-tuning/linux/#toc-anchor-2 and the
  # cromwell-intl / IBM TCP tuning guides.
  #
  # GKE node defaults (as of 2023-04-19), for reference:
  #   net.core.netdev_max_backlog=1000   net.core.rmem_max=212992
  #   net.core.wmem_max=212992           net.ipv4.tcp_rmem=4096 87380 6291456
  #   net.ipv4.tcp_wmem=4096 16384 4194304   net.core.somaxconn=4096
  #
  # Settings (reviewed 2026-06-29 against the live core node):
  #   - net.core.netdev_max_backlog=30000: deeper NIC ingress queue so bursts to
  #     the shared node don't get dropped before the kernel drains them.
  #   - net.core.rmem_max / wmem_max = 32MiB: socket-buffer ceiling matched to the
  #     tcp_rmem/tcp_wmem autotuning max. Going higher than autotuning uses buys
  #     nothing.
  #   - net.ipv4.tcp_rmem / tcp_wmem = "4096 <default> 33554432": the min / default
  #     / 32MiB-max autotuning windows. Read default 87380, write default 16384.
  #   - net.ipv4.tcp_tw_reuse=1: the node reuses TIME_WAIT sockets for new outbound
  #     connections (proxy/nginx -> upstream churn) so it doesn't run out of
  #     ephemeral ports under load.
  #
  # NOT applied: net.ipv4.tcp_max_syn_backlog and
  # net.ipv4.tcp_slow_start_after_idle are NOT on GKE's node-system-config
  # allowlist (would be rejected at apply, and tg plan won't catch it). They are
  # also not kubelet "safe" sysctls, so they can't be set per-pod via
  # securityContext either. The SYN-storm case the former targeted is already
  # covered by tcp_syncookies (on by default); the latter's benefit is marginal
  # on the sub-ms LB->node path. ip_local_port_range stays scoped to the chp pod
  # in hub/values.yaml (a "safe" sysctl), not set node-wide here.
  #
  # rmem/wmem values are in bytes; here be dragons.
  linux_node_sysctls = {
    "net.core.netdev_max_backlog" = "30000"
    "net.core.rmem_max"           = "33554432"
    "net.core.wmem_max"           = "33554432"
    "net.ipv4.tcp_rmem"           = "4096 87380 33554432"
    "net.ipv4.tcp_wmem"           = "4096 16384 33554432"
    "net.ipv4.tcp_tw_reuse"       = "1"
  }

  resource_labels = {
    hub                   = "core"
    "nodepool-deployment" = "core"
  }
}
