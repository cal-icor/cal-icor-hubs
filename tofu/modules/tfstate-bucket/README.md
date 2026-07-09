# tofu/modules/tfstate-bucket: the remote-state bucket

Manages the single GCS bucket that holds every unit's OpenTofu state, including
its own.

This bucket **must** be created before anything is deployed via terragrunt.

## Why it is safe to manage its own backend

This unit's state lives at `bootstrap/tfstate-bucket/` inside the bucket it
manages. That is only a problem on destroy, which would delete the bucket out
from under every other unit's state. Two settings block that:

- `prevent_destroy = true` stops `tofu destroy` from touching the bucket.
- `force_destroy = false` refuses to delete the bucket while it still holds
  objects (which it always will, since it holds all the state).

Normal `plan`/`apply` runs are unaffected.

<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_google"></a> [google](#provider\_google) | n/a |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [google_storage_bucket.state](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_bucket_name"></a> [bucket\_name](#input\_bucket\_name) | Name of the GCS bucket holding OpenTofu remote state. | `string` | n/a | yes |
| <a name="input_labels"></a> [labels](#input\_labels) | Billing labels; 'networking' matches the network module's rollup. | `map(string)` | <pre>{<br/>  "hub": "networking"<br/>}</pre> | no |
| <a name="input_location"></a> [location](#input\_location) | Bucket location; same region as the cluster. | `string` | `"US-CENTRAL1"` | no |
| <a name="input_soft_delete_retention_seconds"></a> [soft\_delete\_retention\_seconds](#input\_soft\_delete\_retention\_seconds) | Soft-delete retention window; 604800 = 7 days. | `number` | `604800` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_bucket_name"></a> [bucket\_name](#output\_bucket\_name) | Name of the remote-state bucket. |
| <a name="output_bucket_url"></a> [bucket\_url](#output\_bucket\_url) | gs:// URL of the remote-state bucket. |
<!-- END_TF_DOCS -->
