# Adopts the remote-state bucket. Global, not cluster-scoped, so it lives under
# bootstrap/; its own state key ("bootstrap/tfstate-bucket") sits in the bucket
# it manages, which prevent_destroy in the module makes safe.
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

terraform {
  source = "../../modules/tfstate-bucket"
}

inputs = {
  bucket_name = "cal-icor-hubs-tofu-state"
  location    = "US-CENTRAL1"
}
