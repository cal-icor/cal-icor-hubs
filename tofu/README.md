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
  spring-2025/                   # live units; one state file each, key derived from path
    network/terragrunt.hcl       # -> state prefix spring-2025/network
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
