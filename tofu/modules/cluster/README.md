# tofu/cluster: reusable GKE cluster

Creates a GKE cluster shell. The default pool is removed; node pools are separate
units sourcing [`modules/nodepools`](../nodepools), where node VM size is set.
Dev and prod share this module.

Manages the cluster's subnet: `node_cidr_block` for node IPs and a secondary
range (`pod_cidr_block`) for pods. Services stay GKE-managed. Node privacy is
set per-pool, not here.

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
| [google_compute_network.cluster](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_network) | resource |
| [google_compute_subnetwork.cluster](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_subnetwork) | resource |
| [google_container_cluster.cluster](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_cluster) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_cluster_name"></a> [cluster\_name](#input\_cluster\_name) | GKE cluster name. Also the unit directory under tofu/. | `string` | n/a | yes |
| <a name="input_create_network"></a> [create\_network](#input\_create\_network) | Create a dedicated VPC named cluster\_name (own-VPC-per-cluster). False attaches the subnet to the existing var.network. | `bool` | `false` | no |
| <a name="input_deletion_protection"></a> [deletion\_protection](#input\_deletion\_protection) | Blocks tofu from deleting the cluster. Set false for clusters CI/CD tears down. | `bool` | `true` | no |
| <a name="input_location"></a> [location](#input\_location) | Cluster location. A region gives a regional cluster. | `string` | `"us-central1"` | no |
| <a name="input_max_pods_per_node"></a> [max\_pods\_per\_node](#input\_max\_pods\_per\_node) | Default max pods per node. | `number` | `110` | no |
| <a name="input_network"></a> [network](#input\_network) | Existing VPC for the cluster and its subnet when create\_network is false. Ignored when create\_network is true. | `string` | `"default"` | no |
| <a name="input_node_cidr_block"></a> [node\_cidr\_block](#input\_node\_cidr\_block) | Primary subnet range for node IPs. | `string` | n/a | yes |
| <a name="input_node_locations"></a> [node\_locations](#input\_node\_locations) | Zones the cluster places nodes in. | `list(string)` | <pre>[<br/>  "us-central1-b"<br/>]</pre> | no |
| <a name="input_pod_cidr_block"></a> [pod\_cidr\_block](#input\_pod\_cidr\_block) | Subnet secondary range for pod IPs. | `string` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region for the cluster's subnet. | `string` | `"us-central1"` | no |
| <a name="input_release_channel"></a> [release\_channel](#input\_release\_channel) | GKE release channel. | `string` | `"REGULAR"` | no |
| <a name="input_resource_labels"></a> [resource\_labels](#input\_resource\_labels) | GCE resource labels on the cluster (billing/rollup). | `map(string)` | `{}` | no |
| <a name="input_subnet_name"></a> [subnet\_name](#input\_subnet\_name) | Subnet name. Null derives it from cluster\_name. | `string` | `null` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_cluster_ca_certificate"></a> [cluster\_ca\_certificate](#output\_cluster\_ca\_certificate) | Base64 cluster CA certificate, for building a kubeconfig. |
| <a name="output_endpoint"></a> [endpoint](#output\_endpoint) | Control-plane API endpoint. |
| <a name="output_location"></a> [location](#output\_location) | Cluster location (region or zone). |
| <a name="output_name"></a> [name](#output\_name) | Cluster name. |
| <a name="output_network_name"></a> [network\_name](#output\_network\_name) | VPC the cluster and its subnet live in. Feeds the network and node-pool units. |
| <a name="output_node_cidr_block"></a> [node\_cidr\_block](#output\_node\_cidr\_block) | Primary subnet range for node IPs. Feeds the NFS allowlist. |
| <a name="output_pod_cidr_block"></a> [pod\_cidr\_block](#output\_pod\_cidr\_block) | Subnet secondary range for pod IPs. Feeds the NFS allowlist. |
| <a name="output_self_link"></a> [self\_link](#output\_self\_link) | Cluster self link. |
| <a name="output_subnet_name"></a> [subnet\_name](#output\_subnet\_name) | Cluster subnet name. |
<!-- END_TF_DOCS -->
