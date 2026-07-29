# spring-2025 units

Live Terragrunt units for the `spring-2025` GKE cluster. Each subdirectory is a
unit with its own state file (key = its path under `tofu/`, e.g.
`clusters/spring-2025/network`). A unit `include`s
[`root.hcl`](../../root.hcl) and sources a module from
[`modules/`](../../modules).

The control plane itself is not managed here. It was created by hand with
`gcloud` before the tofu conversion, so there is no `cluster/` unit and a destroy
takes out the pools and the network but never the cluster.

The units:

- [`network/`](network) sources [`modules/network`](../../modules/network): Cloud Router, Cloud NAT, reserved egress IP, and the IAP-SSH firewall.
- [`prometheus-pool/`](prometheus-pool) sources [`modules/nodepools`](../../modules/nodepools): `prometheus-pool-2026-06-29` (`n2-standard-8`) for `prometheus-server`.
- [`core-pool/`](core-pool) sources [`modules/nodepools`](../../modules/nodepools): `core-pool-2026-06-30` (`n2-standard-8`) for every hub's hub/proxy pods and the shared ingress-nginx controller.
- [`support-pool/`](support-pool) sources [`modules/nodepools`](../../modules/nodepools): `support-pool-2026-07-07` (`n2-standard-4`) for the shared cluster services and the in-cluster NFS server.
- [`user-pool/`](user-pool) sources [`modules/nodepools`](../../modules/nodepools): `user-pool-2026-07-07` (`n2-highmem-8`) for the student singleuser servers, tainted `hub.jupyter.org_dedicated=user:NoSchedule`.
- [`workshop-pool/`](workshop-pool) sources [`modules/nodepools`](../../modules/nodepools): `workshop-pool-2026-07-07` (`n2d-highmem-16`), a second user pool for workshops with the same `user` taint, normally scaled to zero (`min 0 / max 2`).

See [`tofu/README.md`](../../README.md) for the full cluster spec. Run
`terragrunt` from inside a unit directory.

The table below is empty because this directory holds only unit wiring, no
resources of its own.

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
