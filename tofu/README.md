# OpenTofu + Terragrunt

Infrastructure for the `spring-2025` GKE cluster, managed with
[OpenTofu](https://opentofu.org/) and orchestrated by
[Terragrunt](https://terragrunt.gruntwork.io/).

## Layout

```bash
tofu/
  root.hcl                       # shared remote-state (GCS) + common inputs (project, region)
  modules/                       # reusable OpenTofu code (no backend/provider state)
    cluster/                     # reusable GKE cluster (pools are separate units)
    network/                     # Cloud Router, NAT, egress IP, IAP-SSH firewall
    nodepools/                   # reusable private GKE node-pool module
    tfstate-bucket/              # the GCS remote-state bucket itself (imported)
  bootstrap/                     # global units, not tied to one cluster
    tfstate-bucket/terragrunt.hcl   # -> bootstrap/tfstate-bucket
  clusters/                      # one dir per cluster (plus the template)
    cluster-template/            # copy to clusters/<cluster-name>/ to stand up a new cluster
      cluster/terragrunt.hcl          # VPC + subnet + GKE cluster
      network/terragrunt.hcl          # Cloud Router, NAT, egress IP, IAP-SSH firewall
      prometheus-pool/terragrunt.hcl  # one private node pool per role
      core-pool/terragrunt.hcl
      support-pool/terragrunt.hcl
      user-pool/terragrunt.hcl
    spring-2025/                 # live units; one state file each, key derived from path
      network/terragrunt.hcl          # -> state prefix clusters/spring-2025/network
      prometheus-pool/terragrunt.hcl  # -> clusters/spring-2025/prometheus-pool
      core-pool/terragrunt.hcl        # -> clusters/spring-2025/core-pool
      support-pool/terragrunt.hcl     # -> clusters/spring-2025/support-pool
      user-pool/terragrunt.hcl        # -> clusters/spring-2025/user-pool
      workshop-pool/terragrunt.hcl    # -> clusters/spring-2025/workshop-pool
```

Each leaf `terragrunt.hcl` is a *unit*: it `include`s `root.hcl` and points at a
module via `terraform { source = "../../../modules/<name>" }`. The unit's path under
`tofu/` becomes its GCS state prefix (e.g. `clusters/spring-2025/network`), so backends
are never hand-written. The key follows the unit's directory, so moving a unit means
relocating its state object in the bucket to the matching prefix.

## Running a unit

Terragrunt drives OpenTofu, so set it to use `tofu` rather than `terraform`:

```bash
export TG_TF_PATH=tofu
cd tofu/clusters/spring-2025/<unit>
terragrunt init
terragrunt plan
terragrunt apply        # mutates real infra; review the plan first
```

`terragrunt` must be on `PATH` (also required by the pre-commit hooks).

## CI

There is no dedicated tofu CI workflow. The tofu hooks (`tofu_fmt`,
`terragrunt_fmt`, `terragrunt_hcl_validate`, `terraform-docs-go`) run locally via
`pre-commit install`; they sit under `ci.skip` in `.pre-commit-config.yaml`, so
pre-commit.ci does not run them on PRs. pre-commit.ci runs the remaining hooks.

`plan`, `apply`, and `destroy` run through
`.github/workflows/deploy-spring-2025-cluster.yaml` (`workflow_dispatch` or
`workflow_call`), which drives `terragrunt run --all` over the
`clusters/spring-2025` units. It authenticates as `prod-infra@` via keyless
Workload Identity Federation; the WIF stack and one-time GCP setup are documented
in the repo-root `CLAUDE.md` deploy-auth section.

## Cluster spec

`spring-2025` runs on the `default` VPC. All node pools are private (internal IPs
only); outbound internet egress goes through the Cloud NAT below. Each pool is a
Terragrunt unit sourcing `modules/nodepools`, and the network plumbing is one
`modules/network` unit.

### Network

`clusters/spring-2025/network` (`modules/network`): Cloud Router
`spring-2025-nat-router`, Cloud NAT `spring-2025-nat`, reserved egress IP
`spring-2025-nat-egress` (`35.254.232.174`), and the `spring-2025-allow-iap-ssh`
firewall (IAP range `35.235.240.0/20`, tcp:22, target tag `hub-cluster`).

### Node pools

All pinned to `us-central1-b`, disk 100 GB unless noted.

| Pool | Machine | Nodes min/max | Runs | Notes |
|------|---------|---------------|------|-------|
| `prometheus-pool-2026-06-29` | `n2-standard-8` | 1 / 3 | `prometheus-server` | 1000Gi `prometheus-data` PD |
| `core-pool-2026-06-30` | `n2-standard-8` | 1 / 3 | every hub's hub + proxy pods, ingress-nginx | `max_pods_per_node=200`, `cpu_manager_policy=static`, TCP sysctls |
| `support-pool-2026-07-07` | `n2-standard-4` | 1 / 3 | cert-manager, kube-state-metrics, grafana, statsd, placeholder-scaler, dirsize reporters, in-cluster NFS server | grafana + `home-nfs` carry zonal PDs |
| `user-pool-2026-07-07` | `n2-highmem-8` | 0 / 3 | student singleuser servers + placeholders | disk 200 GB, `location_policy=ANY`, taint `hub.jupyter.org_dedicated=user:NoSchedule` |
| `workshop-pool-2026-07-07` | `n2d-highmem-16` | 0 / 2 | workshop singleuser servers | disk 200 GB, same `user` taint, normally scaled to zero |

`gpu-pool` is idle (scaled to zero) and not tofu-managed.

## State bucket

`bootstrap/tfstate-bucket` manages the GCS bucket that holds every unit's state,
including its own. The bucket was created by hand before the tofu conversion, so
the unit adopts it with `terragrunt import` rather than creating it, and a clean
`plan` afterward is the sign the config matches. `prevent_destroy` and
`force_destroy = false` in `modules/tfstate-bucket` keep a stray `destroy` from
deleting the bucket that all the other state lives in. It also pins the settings
that were only clicked once at creation: uniform bucket-level access, public
access prevention set to `enforced`, object versioning, a 7-day soft-delete
window, and the `hub = networking` billing label.

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
