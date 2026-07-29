# tofu/modules/network: Cloud Router + NAT

The outbound egress path for a cluster's private nodes: a
[Cloud Router](https://cloud.google.com/network-connectivity/docs/router/concepts/overview),
a [Cloud NAT](https://cloud.google.com/nat/docs/overview) gateway, a reserved
static egress IP, and the IAP-SSH firewall rule.

Every resource name is a required input, so one module serves every cluster.
Units pass `<cluster-name>-nat-router`, `-nat`, `-nat-egress` and
`-allow-iap-ssh`, which keeps a dev cluster's plumbing from colliding with
prod's. Live units:
[`clusters/spring-2025/network`](../../clusters/spring-2025/network) and
[`clusters/dev/network`](../../clusters/dev/network).

This module ships its own [`provider.tf`](provider.tf), unlike
[`modules/nodepools`](../nodepools), to put the `hub = networking` default label
on everything it creates for the billing rollup.

## What it does not touch

The inbound ingress IP (`34.56.76.244`, `wildcard-dns-target-spring-2025` on
`spring-2025`), the ingress-nginx LoadBalancer, the `loadBalancerIP` in
[`support/values.yaml`](../../../support/values.yaml), and the Infoblox wildcard
DNS. Those are inbound and independent of NAT.

## NAT config

Four settings in [`main.tf`](main.tf)
([resource docs](https://search.opentofu.org/provider/hashicorp/google/latest/docs/resources/compute_router_nat))
to understand before changing them:

- `nat_ip_allocate_option = "MANUAL_ONLY"`, pinned to the reserved address, so
  the cluster has one stable outbound source IP to document and allowlist. Read
  it after apply with `terragrunt output nat_egress_ip`.
- `source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"`, which
  covers the GKE pod secondary range. Pod egress is the whole reason the NAT is
  there, so narrowing this to node primary IPs would break it.
- [`enable_dynamic_port_allocation`](https://cloud.google.com/nat/docs/ports-and-addresses#dynamic-port-allocation)
  `= true`, 64 to 2048 ports per VM. A multi-tenant JupyterHub node runs many
  pods opening outbound connections, and a fixed allocation runs them out of
  source ports. That surfaces as intermittent egress failures which are hard to
  diagnose.
- NAT logging is on, filtered to `ERRORS_ONLY`.

## IAP SSH firewall rule

[`firewall.tf`](firewall.tf) adds `<cluster-name>-allow-iap-ssh`: an INGRESS rule
letting Google's
[IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
range (`35.235.240.0/20`) reach tcp:22 on nodes carrying the `hub-cluster` tag.

Private nodes have no external IP, so SSH tunnels through IAP:

```sh
gcloud compute ssh <node> --zone=<zone> --tunnel-through-iap
```

That also needs `roles/iap.tunnelResourceAccessor`. Scoping the rule to the IAP
range and the node tag keeps access control at the IAP layer, so granting or
revoking access is an IAM change rather than a firewall source-IP edit.

## Normal workflow

Run this module through a unit, never directly. The unit supplies the backend
(via [`root.hcl`](../../root.hcl)) and the inputs. Set `export TG_TF_PATH=tofu`
first; see the top-level [`tofu/README.md`](../../README.md).

```sh
cd tofu/clusters/spring-2025/network
terragrunt init      # wires the gcs backend, downloads the google provider
terragrunt plan
terragrunt apply     # creates router + NAT + egress IP (requires approval)
terragrunt output nat_egress_ip
```

`terragrunt init` needs the state bucket to already exist. That is a one-time,
per-project step: see [`modules/tfstate-bucket`](../tfstate-bucket).

## Do not destroy

Every pool runs private nodes whose only path to the non-Google internet is this
gateway. Destroying it breaks image pulls from non-Google registries and all
student notebook egress.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.7 |
| <a name="requirement_google"></a> [google](#requirement\_google) | ~> 6.0 |

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_google"></a> [google](#provider\_google) | 6.50.0 |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [google_compute_address.nat_egress](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_address) | resource |
| [google_compute_firewall.iap_ssh](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_firewall) | resource |
| [google_compute_router.nat_router](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_router) | resource |
| [google_compute_router_nat.nat](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_router_nat) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_iap_source_range"></a> [iap\_source\_range](#input\_iap\_source\_range) | Google IAP TCP forwarding source range, for SSH to private nodes via --tunnel-through-iap. | `string` | `"35.235.240.0/20"` | no |
| <a name="input_iap_ssh_firewall_name"></a> [iap\_ssh\_firewall\_name](#input\_iap\_ssh\_firewall\_name) | Name of the firewall rule allowing IAP-tunneled SSH to cluster nodes. | `string` | n/a | yes |
| <a name="input_nat_egress_ip_name"></a> [nat\_egress\_ip\_name](#input\_nat\_egress\_ip\_name) | Name of the reserved static egress IP used by Cloud NAT (outbound only). | `string` | n/a | yes |
| <a name="input_nat_name"></a> [nat\_name](#input\_nat\_name) | Name of the Cloud NAT gateway. | `string` | n/a | yes |
| <a name="input_network"></a> [network](#input\_network) | VPC network the cluster runs on. | `string` | n/a | yes |
| <a name="input_node_tag"></a> [node\_tag](#input\_node\_tag) | Network tag carried by every node pool in the cluster; firewall target for IAP SSH. | `string` | `"hub-cluster"` | no |
| <a name="input_project"></a> [project](#input\_project) | GCP project hosting the cluster. | `string` | `"cal-icor-hubs"` | no |
| <a name="input_region"></a> [region](#input\_region) | Region for the Cloud Router, Cloud NAT, and egress IP. | `string` | `"us-central1"` | no |
| <a name="input_router_name"></a> [router\_name](#input\_router\_name) | Name of the Cloud Router that hosts the NAT config. | `string` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_iap_ssh_firewall_name"></a> [iap\_ssh\_firewall\_name](#output\_iap\_ssh\_firewall\_name) | Firewall rule allowing IAP-tunneled SSH (tcp:22 from 35.235.240.0/20) to cluster nodes once they go private. |
| <a name="output_nat_egress_ip"></a> [nat\_egress\_ip](#output\_nat\_egress\_ip) | Stable outbound egress IP for all private-node traffic to the public internet. Document/allowlist this where needed. Distinct from the inbound ingress IP 34.56.76.244. |
| <a name="output_nat_name"></a> [nat\_name](#output\_nat\_name) | Cloud NAT gateway name. |
| <a name="output_router_name"></a> [router\_name](#output\_router\_name) | Cloud Router hosting the NAT config. |
<!-- END_TF_DOCS -->
