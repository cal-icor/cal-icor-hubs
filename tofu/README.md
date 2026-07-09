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

`.github/workflows/tofu-ci.yaml` runs on PRs that touch `tofu/`. Right now it has
one job: run pre-commit on the changed files.

`plan` and `apply` will be done in a new workflow, and the identity will be
re-scoped.

One-time GCP setup (run once, needs an IAM admin):

```bash
gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project=cal-icor-hubs

gcloud iam workload-identity-pools create github \
  --project=cal-icor-hubs --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github \
  --project=cal-icor-hubs --location=global --workload-identity-pool=github \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == 'cal-icor'"

# Read-only, scoped to this repo's federated identity.
gcloud projects add-iam-policy-binding cal-icor-hubs \
  --role="roles/viewer" \
  --member="principalSet://iam.googleapis.com/projects/1045396016572/locations/global/workloadIdentityPools/github/attribute.repository/cal-icor/cal-icor-hubs"
```

The `attribute-condition` locks the pool to the `cal-icor` org and the
`principalSet` binding to this one repo, so no other repo can use it. The provider
resource name in the workflow is
`projects/1045396016572/locations/global/workloadIdentityPools/github/providers/github`.

## Private node migration

These units back the staged migration of the `spring-2025` cluster from public to
private nodes (each new pool gets `enable_private_nodes = true`; egress flows
through the Cloud NAT below). New pools are built alongside the old ones and the
workloads are drained over, rather than flipped in place. Keep this section
current as each phase lands.

| Phase | Unit / module | What it does | Status |
|-------|---------------|--------------|--------|
| A | `clusters/spring-2025/network` (`modules/network`) | Cloud Router + Cloud NAT + reserved egress IP `35.254.232.174`, so private nodes can reach the public internet. | Applied / live |
| 0 | `clusters/spring-2025/network` (`modules/network`, `firewall.tf`) | `spring-2025-allow-iap-ssh` firewall (IAP range `35.235.240.0/20`, tcp:22) so `gcloud compute ssh --tunnel-through-iap` still works once nodes lose external IPs. | Applied / live |
| 1 | `clusters/spring-2025/prometheus-pool` (`modules/nodepools`) | Private `prometheus-pool-2026-06-29` (canary). `prometheus-server` moved onto it (PD reattached across pools); old public `prometheus-pool-2025-12-22` deleted. | Complete |
| 2 | `clusters/spring-2025/core-pool` (`modules/nodepools`) | Private `core-pool-2026-06-30` for every hub's hub/proxy pods plus the shared ingress-nginx controller. `n2-standard-8` (right-sized down from the old pool's `n2-highmem-8` — the workload requested only 35% CPU / 27% mem there; halves RAM 64->32 GB while keeping 8 vCPU for redeploy headroom), `max_pods_per_node = 200`, `cpu_manager_policy = static`, plus the TCP/IP node sysctls. | Complete (2026-07-06 — pool applied, all 42 hubs + ingress cut over via #844, old public `core-pool-2026-03-05` drained + deleted) |
| 3 | `clusters/spring-2025/support-pool` (`modules/nodepools`) | Private `support-pool-2026-07-07` for the shared cluster services (cert-manager, kube-state-metrics, grafana, statsd, node-placeholder-scaler, per-hub dirsize reporters) and the in-cluster NFS server. `n2-standard-4`, module defaults otherwise. **Maintenance window**: the NFS server (`home-nfs`) and grafana carry RWO zonal PDs in `us-central1-b`; moving the NFS server freezes home dirs cluster-wide ~1-3 min. `home-nfs` ships `strategy=RollingUpdate` (not exposed for override by the chart), so its move is handled out of band (patch to `Recreate` / scale-to-0) to avoid a Multi-Attach deadlock. | Complete (2026-07-07 — pool applied, all support singletons + NFS server + all 42 hubs' dirsize reporters cut over via #857, `home-nfs` PD moved with no Multi-Attach via a pre-merge `Recreate` patch, old public `support-pool-2026-02-12` drained + deleted) |
| 4 | `clusters/spring-2025/user-pool` (`modules/nodepools`) | Private `user-pool-2026-07-07` for the student singleuser notebook servers (the only pool with a taint, `hub.jupyter.org_dedicated=user:NO_SCHEDULE`) plus the placeholder-scaler's warm spares. `n2-highmem-8`, disk 200 GB, autoscale `min 0 / max 3`, `location_policy = ANY` (all mirroring the live `user-base`). **Graceful cutover, no window**: draining would kill live sessions, so the old pool is not drained. The singleuser + placeholder nodeSelectors are repointed to the new pool (`base-pool` -> `user-pool-2026-07-07`), new spawns land private, and the old `user-base` pool is cordoned and left to empty via the culler (idle 30m / maxAge 12h) before deletion. | Complete (2026-07-07: pool applied, all 22 hubs' singleuser + placeholder nodeSelectors cut over via #860, new spawns verified private on staging + prod, old public `user-base` cordoned then deleted once its last session logged out). This was the final phase: every pool on the cluster now runs private nodes with Cloud NAT egress. |

The `gpu-pool` is excluded from the migration (idle / scaled to zero).

`clusters/spring-2025/workshop-pool` (`workshop-pool-2026-07-07`) is a post-migration addition, not a phase: a second private user pool dedicated to workshops, normally scaled to zero. See `clusters/spring-2025/README.md`.

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
