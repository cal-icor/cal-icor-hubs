# spring-2025 units

Live Terragrunt units for the `spring-2025` GKE cluster. Each subdirectory is a
unit with its own state file (key = its path under `tofu/`, e.g.
`clusters/spring-2025/network`). A unit `include`s `../../../root.hcl` and sources a module
from `../../../modules/`.

The units:

- `network/` sources `modules/network`: Cloud Router, Cloud NAT, reserved egress IP, and the IAP-SSH firewall.
- `prometheus-pool/` sources `modules/nodepools`: private `prometheus-pool-2026-06-29` for `prometheus-server`.
- `core-pool/` sources `modules/nodepools`: private `core-pool-2026-06-30` for every hub's hub/proxy pods and the shared ingress-nginx controller.
- `support-pool/` sources `modules/nodepools`: private `support-pool-2026-07-07` for the shared cluster services and the in-cluster NFS server.
- `user-pool/` sources `modules/nodepools`: private `user-pool-2026-07-07` for the student singleuser servers (tainted `...=user`).
- `workshop-pool/` sources `modules/nodepools`: private `workshop-pool-2026-07-07`, a second user pool dedicated to workshops (same `...=user` taint, so routing is a nodeSelector-only change). Normally scaled to zero (`n2d-highmem-16`, `initial/min 0`, `max 2`); spun up only for a scheduled workshop.

See `../README.md` for the phase-by-phase migration table.

Run `terragrunt` from inside a unit directory (see `../README.md`).

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
