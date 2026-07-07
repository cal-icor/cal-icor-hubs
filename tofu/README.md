# OpenTofu + Terragrunt

Infrastructure for the `spring-2025` GKE cluster, managed with
[OpenTofu](https://opentofu.org/) and orchestrated by
[Terragrunt](https://terragrunt.gruntwork.io/).

## Layout

```bash
tofu/
  root.hcl                       # shared remote-state (GCS) + common inputs (project, region)
  modules/                       # reusable OpenTofu code (no backend/provider state)
    network/                     # Cloud Router, NAT, egress IP, IAP-SSH firewall
    nodepools/                   # reusable private GKE node-pool module
  spring-2025/                   # live units; one state file each, key derived from path
    network/terragrunt.hcl          # -> state prefix spring-2025/network
    prometheus-pool/terragrunt.hcl  # -> spring-2025/prometheus-pool
    core-pool/terragrunt.hcl        # -> spring-2025/core-pool
```

Each leaf `terragrunt.hcl` is a *unit*: it `include`s `root.hcl` and points at a
module via `terraform { source = "../../modules/<name>" }`. The unit's path under
`tofu/` becomes its GCS state prefix (e.g. `spring-2025/network`), so backends are
never hand-written and state keys stay stable.

## Running a unit

Terragrunt drives OpenTofu, so set it to use `tofu` rather than `terraform`:

```bash
export TG_TF_PATH=tofu
cd tofu/spring-2025/network
terragrunt init
terragrunt plan
terragrunt apply        # mutates real infra; review the plan first
```

`terragrunt` must be on `PATH` (also required by the pre-commit hooks).

## Private node migration

These units back the staged migration of the `spring-2025` cluster from public to
private nodes (each new pool gets `enable_private_nodes = true`; egress flows
through the Cloud NAT below). New pools are built alongside the old ones and the
workloads are drained over, rather than flipped in place. Keep this section
current as each phase lands.

| Phase | Unit / module | What it does | Status |
|-------|---------------|--------------|--------|
| A | `spring-2025/network` (`modules/network`) | Cloud Router + Cloud NAT + reserved egress IP `35.254.232.174`, so private nodes can reach the public internet. | Applied / live |
| 0 | `spring-2025/network` (`modules/network`, `firewall.tf`) | `spring-2025-allow-iap-ssh` firewall (IAP range `35.235.240.0/20`, tcp:22) so `gcloud compute ssh --tunnel-through-iap` still works once nodes lose external IPs. | Applied / live |
| 1 | `spring-2025/prometheus-pool` (`modules/nodepools`) | Private `prometheus-pool-2026-06-29` (canary). `prometheus-server` moved onto it (PD reattached across pools); old public `prometheus-pool-2025-12-22` deleted. | Complete |
| 2 | `spring-2025/core-pool` (`modules/nodepools`) | Private `core-pool-2026-06-30` for every hub's hub/proxy pods plus the shared ingress-nginx controller. `n2-standard-8` (right-sized down from the old pool's `n2-highmem-8` — the workload requested only 35% CPU / 27% mem there; halves RAM 64->32 GB while keeping 8 vCPU for redeploy headroom), `max_pods_per_node = 200`, `cpu_manager_policy = static`, plus the TCP/IP node sysctls. | Complete (2026-07-06 — pool applied, all 42 hubs + ingress cut over via #844, old public `core-pool-2026-03-05` drained + deleted) |
| 3 | `spring-2025/support-pool` (`modules/nodepools`) | Private `support-pool-2026-07-07` for the shared cluster services (cert-manager, kube-state-metrics, grafana, statsd, node-placeholder-scaler, per-hub dirsize reporters) and the in-cluster NFS server. `n2-standard-4`, module defaults otherwise. **Maintenance window**: the NFS server (`home-nfs`) and grafana carry RWO zonal PDs in `us-central1-b`; moving the NFS server freezes home dirs cluster-wide ~1-3 min. `home-nfs` ships `strategy=RollingUpdate` (not exposed for override by the chart), so its move is handled out of band (patch to `Recreate` / scale-to-0) to avoid a Multi-Attach deadlock. | IaC authored; pool `tg apply` + helm nodeSelector cutover pending (pre-login window) |

The `gpu-pool` is excluded from the migration (idle / scaled to zero). `user-pool`
follows as the final phase.

<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

No providers.

## Modules

No modules.

## Resources

No resources.

## Inputs

No inputs.

## Outputs

No outputs.
<!-- END_TF_DOCS -->
