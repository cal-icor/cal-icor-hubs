# dev units

Live Terragrunt units for the `dev` GKE cluster: a throwaway, keyless-CI cluster
for the end-to-end deploy pilot. Unlike `spring-2025`, this cluster is created by
tofu (the `cluster/` unit), so the pools take the name from
`dependency.cluster.outputs.name` rather than a hand-declared `cluster.hcl`.

Each subdirectory is a unit with its own state file (key = its path under
`tofu/`, e.g. `clusters/dev/network`). A unit `include`s `../../../root.hcl` and
sources a module from `../../../modules/`.

The units:

- `cluster/` sources `modules/cluster`: its own VPC (`create_network = true`),
  the subnet, and the zonal GKE cluster in `us-central1-b`. Fresh ranges
  (`10.10.0.0/22` nodes, `10.96.0.0/14` pods) that cannot collide with prod's
  default network. `deletion_protection = false` so CI can tear it down.
- `network/` sources `modules/network`: Cloud Router, Cloud NAT, reserved egress
  IP, and the IAP-SSH firewall. Depends on `cluster/`.
- `core-pool/` sources `modules/nodepools`: private `core-pool` (`e2-standard-2`)
  for the dev hub's hub/proxy pods and the ingress-nginx controller.
- `support-pool/` sources `modules/nodepools`: private `support-pool`
  (`e2-standard-2`) for the shared cluster services and the in-cluster NFS server.
- `prometheus-pool/` sources `modules/nodepools`: private `prometheus-pool`
  (`e2-medium`) for `prometheus-server`.
- `user-pool/` sources `modules/nodepools`: private `user-pool` (`e2-medium`,
  `min 0 / max 1`) for the single dev user's singleuser server (tainted `...=user`).

Everything is downsized from the `spring-2025` baseline: `e2` machine types, 50 GB
boot disks, tight `max_nodes`, and one user. See each unit for the per-pool notes.

## Standing it up

```bash
export TG_TF_PATH=tofu
cd tofu/clusters/dev
terragrunt run-all plan      # cluster, then network, then the pools
terragrunt run-all apply     # mutates real infra; review the plan first
```

`run-all` walks the `dependency` graph: `cluster/` first, then `network/`, then
the pools. To drive a single unit, `cd` into it and run `terragrunt plan`/`apply`.

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
