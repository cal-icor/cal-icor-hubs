# spring-2025 units

Live Terragrunt units for the `spring-2025` GKE cluster. Each subdirectory is a
unit with its own state file (key = its path under `tofu/`, e.g.
`spring-2025/network`). A unit `include`s `../../root.hcl` and sources a module
from `../../modules/`.

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
