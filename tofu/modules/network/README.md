# tofu/network: Cloud Router + NAT for spring-2025

This root module creates the **outbound** egress path that private nodes need:
a Cloud Router, a Cloud NAT gateway, and a reserved static egress IP.

## What this does and does not touch

- Creates: `spring-2025-nat-router`, `spring-2025-nat`, and the reserved egress
  IP `spring-2025-nat-egress`.
- Does **not** touch the inbound ingress IP `34.56.76.244`
  (`wildcard-dns-target-spring-2025`), the ingress-nginx LoadBalancer, the
  `support/values.yaml` `loadBalancerIP`, or the Infoblox wildcard DNS. Those
  are inbound and independent of NAT.
- Additive only: nodes are still public until later phases. Creating NAT now is
  safe and changes nothing about existing traffic.

## IAP SSH firewall rule

`firewall.tf` adds `spring-2025-allow-iap-ssh`: an INGRESS rule permitting
Google's IAP TCP forwarding range (`35.235.240.0/20`) to reach tcp:22 on cluster
nodes (target tag `hub-cluster`).

This is **additive and changes nothing while nodes are public** — direct
`gcloud compute ssh` over a node's external IP keeps working via the existing
broad `allow-ssh` rule. The IAP rule matters once a pool goes private: a private
node has no external IP, so SSH must tunnel through IAP
(`gcloud compute ssh <node> --zone=us-central1-b --tunnel-through-iap`, plus
`roles/iap.tunnelResourceAccessor`). Scoping the rule to the IAP range and the
node tag also lets the broad `allow-ssh` rule be narrowed or removed later in the
access lock-down without losing operator SSH.

## NAT egress IP

`MANUAL_ONLY` pinned to the reserved static IP `spring-2025-nat-egress`, so the
cluster has one stable, documentable outbound source IP. Read it after apply
with `tofu output nat_egress_ip`.

## First-time bootstrap (run once, requires approval)

The GCS backend needs its bucket to exist before `tofu init`:

```sh
gcloud storage buckets create gs://cal-icor-hubs-tofu-state \
  --project=cal-icor-hubs --location=us-central1 \
  --uniform-bucket-level-access \
  --labels=hub=networking
gcloud storage buckets update gs://cal-icor-hubs-tofu-state --versioning
```

The `hub=networking` label keeps the state bucket in the same billing rollup as
the rest of the network plumbing. The bucket cannot be created by this module
(it has to exist before `tofu init`), so the label is set here at bootstrap.

## Normal workflow

This module is run through its live unit `clusters/spring-2025/network`, which supplies the
backend and provider via Terragrunt (`export TG_TF_PATH=tofu` first, see the top
`tofu/README.md`):

```sh
cd tofu/clusters/spring-2025/network
terragrunt init      # wires the gcs backend, downloads the google provider
terragrunt plan      # first apply expected: 3 to add, 0 to change, 0 to destroy
terragrunt apply     # creates router + NAT + egress IP (requires approval)
terragrunt output nat_egress_ip
```

## Rollback

The private-node migration is complete, so the NAT is now load-bearing: every
pool runs private nodes whose only path to the public internet is this gateway.
Destroying it would break image pulls from non-Google registries and all student
notebook egress. Do not `terragrunt destroy` this unit unless the cluster is
first moved back to public nodes. During the original Phase A (nodes still
public) removal was harmless; that is no longer the case.

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
