# Modules

Reusable OpenTofu modules. These hold resource definitions only — no `backend`
or remote-state config. State and provider wiring come from Terragrunt: each
live unit under `tofu/spring-2025/` sources a module here and supplies its own
backend (via `root.hcl`) and inputs.

Add a new module as `modules/<name>/`, then create a unit
`tofu/<cluster>/<name>/terragrunt.hcl` that points at it.

Modules here:

- `network/`: Cloud Router, Cloud NAT, reserved egress IP, and the IAP-SSH firewall.
- `nodepools/`: reusable private GKE node-pool module (one pool per unit).

The table below is empty because this directory contains no resources of its
own; see each subdirectory's README (`network/`, `nodepools/`) for the real docs.

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
