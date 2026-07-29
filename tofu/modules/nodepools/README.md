# tofu/modules/nodepools: private GKE node pools for spring-2025

A reusable module that creates one private node pool on the `spring-2025`
cluster. Nodes get internal IPs only, so outbound traffic flows through the
Cloud NAT from [`modules/network`](../network).

## Per-pool inputs

Each pool is a unit under
[`tofu/clusters/spring-2025/`](../../clusters/spring-2025) that calls this
module. Shared config lives in the module defaults; a unit sets only its
pool-specific values (machine type, sizing, taints, labels) plus:

- `enable_private_nodes = true`
- a date-stamped `pool_name` (house style `<role>-pool-YYYY-MM-DD`)

`pool_name` is also written as the `hub.jupyter.org/pool-name` node label, which
helm `nodeSelector`s pin. Read `pool_name_selector` from the outputs for the
exact `key=value` to set in the paired helm change.

## Zone pinning

`node_locations` must be the single zone where the pool's stateful PD lives
(`us-central1-b` for both prometheus-data and the NFS disk) so pods can reattach
their disks after moving pools.

## Provider and versions

This module ships no `provider.tf` or `versions.tf`; Terragrunt generates them
from [`tofu/root.hcl`](../../root.hcl). Run it through a unit, not directly.

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
| [google_container_node_pool.pool](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_node_pool) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_cluster"></a> [cluster](#input\_cluster) | Name of the GKE cluster this node pool belongs to. | `string` | n/a | yes |
| <a name="input_cpu_manager_policy"></a> [cpu\_manager\_policy](#input\_cpu\_manager\_policy) | kubelet CPU manager policy: "static" pins whole cores to Guaranteed-QoS integer-CPU pods; null/"none" shares all cores. Set "static" for the core pool. | `string` | `null` | no |
| <a name="input_disk_size_gb"></a> [disk\_size\_gb](#input\_disk\_size\_gb) | Boot disk size in GB. | `number` | `100` | no |
| <a name="input_disk_type"></a> [disk\_type](#input\_disk\_type) | Boot disk type. | `string` | `"pd-balanced"` | no |
| <a name="input_enable_private_nodes"></a> [enable\_private\_nodes](#input\_enable\_private\_nodes) | Whether nodes get internal IPs only (no external IP); egress then flows through the Cloud NAT in modules/network. Set per-pool because the cluster-level flag is off. | `bool` | `true` | no |
| <a name="input_extra_node_labels"></a> [extra\_node\_labels](#input\_extra\_node\_labels) | Additional Kubernetes node labels merged in alongside the always-set hub.jupyter.org/pool-name label. | `map(string)` | `{}` | no |
| <a name="input_image_type"></a> [image\_type](#input\_image\_type) | Node image type. | `string` | `"COS_CONTAINERD"` | no |
| <a name="input_initial_node_count"></a> [initial\_node\_count](#input\_initial\_node\_count) | Number of nodes created per zone when the pool is first created. The existing pools were created with 1. | `number` | `1` | no |
| <a name="input_insecure_kubelet_readonly_port_enabled"></a> [insecure\_kubelet\_readonly\_port\_enabled](#input\_insecure\_kubelet\_readonly\_port\_enabled) | Whether the unauthenticated kubelet read-only port (10255) is open, as the string "TRUE" or "FALSE". The existing pools have it disabled; keep "FALSE". | `string` | `"FALSE"` | no |
| <a name="input_linux_node_sysctls"></a> [linux\_node\_sysctls](#input\_linux\_node\_sysctls) | Kernel sysctls applied to the nodes via linux\_node\_config. Empty omits the block; the core pool passes its TCP/IP tuning values. | `map(string)` | `{}` | no |
| <a name="input_location"></a> [location](#input\_location) | Pool location: the cluster's own location, a region for a regional cluster or a zone for a zonal one. A node pool's location must equal its cluster's, so wire this to the cluster module's location output. Defaults (null) to var.region, so the existing spring-2025 regional pools, which pass nothing, keep their region. | `string` | `null` | no |
| <a name="input_location_policy"></a> [location\_policy](#input\_location\_policy) | Autoscaler location policy. BALANCED matches the existing pools. | `string` | `"BALANCED"` | no |
| <a name="input_machine_type"></a> [machine\_type](#input\_machine\_type) | Compute machine type for the pool's nodes (e.g. n2-standard-8). | `string` | n/a | yes |
| <a name="input_max_nodes"></a> [max\_nodes](#input\_max\_nodes) | Autoscaler maximum node count. | `number` | n/a | yes |
| <a name="input_max_pods_per_node"></a> [max\_pods\_per\_node](#input\_max\_pods\_per\_node) | Maximum pods schedulable per node. | `number` | `110` | no |
| <a name="input_min_nodes"></a> [min\_nodes](#input\_min\_nodes) | Autoscaler minimum node count. | `number` | n/a | yes |
| <a name="input_node_locations"></a> [node\_locations](#input\_node\_locations) | Zones the pool places nodes in. Must be a single zone matching any attached zonal PD (prometheus-data and the NFS disk are both in us-central1-b) so stateful pods can reattach. | `list(string)` | <pre>[<br/>  "us-central1-b"<br/>]</pre> | no |
| <a name="input_node_service_account"></a> [node\_service\_account](#input\_node\_service\_account) | Service account for the nodes. The existing pools use the default compute SA. | `string` | `"default"` | no |
| <a name="input_node_tags"></a> [node\_tags](#input\_node\_tags) | Network tags on the nodes. hub-cluster is the custom cluster-wide tag the firewall rules (including the IAP-SSH rule) target. | `list(string)` | <pre>[<br/>  "hub-cluster"<br/>]</pre> | no |
| <a name="input_node_taints"></a> [node\_taints](#input\_node\_taints) | Kubernetes node taints. Empty for nodeSelector-scheduled pools (prometheus/core/support); the user pool sets hub.jupyter.org\_dedicated=user:NO\_SCHEDULE. | <pre>list(object({<br/>    key    = string<br/>    value  = string<br/>    effect = string<br/>  }))</pre> | `[]` | no |
| <a name="input_oauth_scopes"></a> [oauth\_scopes](#input\_oauth\_scopes) | OAuth scopes for the node service account. Defaults to the six GKE default scopes carried by the existing pools. | `list(string)` | <pre>[<br/>  "https://www.googleapis.com/auth/devstorage.read_only",<br/>  "https://www.googleapis.com/auth/logging.write",<br/>  "https://www.googleapis.com/auth/monitoring",<br/>  "https://www.googleapis.com/auth/service.management.readonly",<br/>  "https://www.googleapis.com/auth/servicecontrol",<br/>  "https://www.googleapis.com/auth/trace.append"<br/>]</pre> | no |
| <a name="input_pool_name"></a> [pool\_name](#input\_pool\_name) | Node pool name. House style is <role>-pool-YYYY-MM-DD, stamped with the day the pool is created. Also used as the value of the hub.jupyter.org/pool-name node label that helm nodeSelectors pin. | `string` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region of the regional cluster. Fallback for the pool's location when var.location is null (the spring-2025 regional pools). Value comes from root.hcl inputs. | `string` | `"us-central1"` | no |
| <a name="input_resource_labels"></a> [resource\_labels](#input\_resource\_labels) | GCE instance labels applied to the nodes (billing/rollup dimension). The repo keys billing on hub; e.g. { hub = "prometheus", nodepool-deployment = "prometheus" }. | `map(string)` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_pool_id"></a> [pool\_id](#output\_pool\_id) | Fully qualified GKE node pool ID. |
| <a name="output_pool_name"></a> [pool\_name](#output\_pool\_name) | Name of the created node pool. |
| <a name="output_pool_name_selector"></a> [pool\_name\_selector](#output\_pool\_name\_selector) | The node label helm nodeSelectors must pin to schedule onto this pool. Use it when updating the paired helm config for this pool. |
<!-- END_TF_DOCS -->
