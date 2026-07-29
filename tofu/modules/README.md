# Modules

Reusable OpenTofu modules. Resource definitions only, with no `backend` or
remote-state config. State and provider wiring come from Terragrunt: each live
unit under [`tofu/clusters/`](../clusters) sources a module here and supplies its
own backend (via [`root.hcl`](../root.hcl)) and inputs.

Add a new module as `modules/<name>/`, then create a unit
`tofu/clusters/<cluster>/<name>/terragrunt.hcl` that points at it.

Modules here:

- [`cluster/`](cluster): reusable GKE cluster (default pool removed; pools are separate units).
- [`network/`](network): Cloud Router, Cloud NAT, reserved egress IP, and the IAP-SSH firewall.
- [`nodepools/`](nodepools): reusable private GKE node-pool module (one pool per unit).
- [`tfstate-bucket/`](tfstate-bucket): the GCS remote-state bucket itself.

The table below is empty because this directory holds no resources of its own.
Each subdirectory's README has the real docs.

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
