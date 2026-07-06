# Phase 2 of the public-to-private node migration: the private replacement for
# the existing public core-pool-2026-03-05.
#
# The core pool runs every hub's hub + proxy pods plus the shared
# support-ingress-nginx controller (the single public ingress fronting all
# hubs). These are stateless Deployments with no attached PDs, so the move is a
# rolling reschedule onto this pool once the helm nodeSelectors are repointed —
# no PD reattach to worry about, unlike prometheus. Brief per-hub login/spawn
# pause during the roll; running user kernels (on the user pool) are untouched.
#
# State key derives from this path: "spring-2025/core-pool". Role-named, not
# date-stamped, so it stays stable across recreations; the date-stamped pool
# NAME lives in inputs below.
#
# Config mirrors the live core-pool-2026-03-05 (describe 2026-06-29), with ONE
# deliberate deviation: machine_type is right-sized n2-highmem-8 -> n2-standard-8.
# Measured on the live n2-highmem-8 core node (2026-07-06): 104 pods requesting
# 2600m CPU (35%) / 15.6 GiB mem (27%), with real usage only 761m CPU (10%) /
# 11.6 GiB (19%). The workload (every hub's hub + proxy pods + the 3 ingress
# replicas + GKE system daemons) is memory-shaped and light on CPU, so the 64 GB
# of RAM was ~2x oversized. n2-standard-8 (8 vCPU / 32 GB, ~28 GiB allocatable)
# halves the RAM to reclaim that waste while KEEPING the full 8 vCPU as headroom
# for full-fleet redeploy spikes (all ~42 hub+proxy pods restarting at once). It
# holds the current 15.6 GiB of requests at ~55% with room for ~19 more hub
# pairs. The 16 GB n2 tiers were ruled out: their ~13 GiB allocatable is below
# the 15.6 GiB of requests, so pods wouldn't schedule.
#
# Other differences from the prometheus unit: max_pods_per_node = 200 (deliberate
# high pod density — each hub runs 2 hub + 2 proxy pods, so the pod count, not
# CPU/RAM, is the binding limit), and cpu_manager_policy = "static" (the core
# pool sets it; immutable on a live pool so it must be matched at creation).

include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../modules/nodepools"
}

inputs = {
  pool_name            = "core-pool-2026-06-30"
  enable_private_nodes = true

  node_locations = ["us-central1-b"]

  machine_type      = "n2-standard-8"
  min_nodes         = 1
  max_nodes         = 3
  disk_size_gb      = 100
  max_pods_per_node = 200

  # cpuManagerPolicy + the sysctls below were previously applied to core out of
  # band via `gcloud ... --system-config-from-file core-pool-sysctl.yaml`. That
  # vendored yaml is being retired; tofu now owns the core pool's node config, so
  # the values live here as the single source of truth. cpu_manager_policy is
  # immutable on a live pool, so it must be set at creation to preserve parity.
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
  # Changes from the original vendored core-pool-sysctl.yaml (2026-06-29 review
  # against the n2-highmem-8 node):
  #   - Dropped net.core.somaxconn=4096: GKE's node default is already 4096, so
  #     it was a no-op. Smaller config is better.
  #   - Lowered rmem_max/wmem_max 64MiB -> 32MiB to match the tcp_rmem/tcp_wmem
  #     autotuning ceilings; a socket-buffer max above the TCP autotuning max
  #     buys nothing.
  #   - Fixed tcp_wmem default 87380 -> 16384 (87380 is the READ default; the
  #     write default should be the smaller GKE/Linux value of 16384).
  #   - Added net.ipv4.tcp_tw_reuse=1: lets the node reuse TIME_WAIT sockets for
  #     new OUTBOUND connections (proxy/nginx -> upstream churn), avoiding
  #     ephemeral-port exhaustion under load.
  #
  # NOT applied, by design: net.ipv4.tcp_max_syn_backlog and
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
