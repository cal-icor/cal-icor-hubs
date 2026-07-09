# Root Terragrunt configuration, included by every unit under tofu/.
#
# It centralizes the two things plain OpenTofu cannot share across separate
# state files:
#
#   1. Remote state. One GCS bucket, with each unit's state key derived from its
#      path under tofu/ (e.g. tofu/clusters/spring-2025/network -> prefix
#      "clusters/spring-2025/network"). Units never hand-write a backend block;
#      the key follows the unit's directory, so moving a unit means relocating
#      its state object to the matching prefix.
#
#   2. Common inputs. project and region are identical for every unit, so they
#      are declared once here and merged into each unit's inputs instead of being
#      repeated as variable defaults in every module.
#
# Per-unit specifics (cluster name, node zone, labels, module source) live in the
# unit's own terragrunt.hcl.

# Project and region appear once here and feed both the generated provider below
# and each unit's inputs, so the literals are never repeated per module.
locals {
  project = "cal-icor-hubs"
  region  = "us-central1"
}

# Keep the provider lock file with the module code (modules/<name>/) instead of
# letting Terragrunt copy a duplicate into every unit. Units that source the same
# module then share one pinned set of provider versions rather than drifting into
# separate per-unit lock files. Relies on units including this config with
# merge_strategy = "deep" so this terraform block combines with their `source`.
terraform {
  copy_terraform_lock_file = false
}

remote_state {
  backend = "gcs"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    bucket = "cal-icor-hubs-tofu-state"
    prefix = path_relative_to_include()
  }
}

# Provider and version-constraint boilerplate, generated into each unit's working
# directory so modules don't hand-copy identical files. A module needing custom
# provider config (modules/network sets default_labels = { hub = "networking" })
# commits its own provider.tf; if_exists = "skip" leaves that file untouched and
# only generates one where the module ships none. New leaf modules (e.g. node
# pools) therefore carry no provider.tf / versions.tf at all.
generate "versions" {
  path      = "versions.tf"
  if_exists = "skip"
  contents  = <<-EOF
    terraform {
      required_version = ">= 1.7"

      required_providers {
        google = {
          source  = "hashicorp/google"
          version = "~> 6.0"
        }
      }
    }
  EOF
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "skip"
  contents  = <<-EOF
    provider "google" {
      project = "${local.project}"
      region  = "${local.region}"
    }
  EOF
}

inputs = {
  project = local.project
  region  = local.region
}
