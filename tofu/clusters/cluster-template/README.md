# cluster-template

A template, not a live unit. It holds a full cluster: the `cluster/` unit plus a
`network/` unit and one unit per node pool, wired with Terragrunt `dependency`
blocks so the whole thing stands up in order.

The units:

- `cluster/` sources `modules/cluster`: the VPC (optional), the subnet, and the
  GKE cluster (default pool removed).
- `network/` sources `modules/network`: Cloud Router, Cloud NAT, egress IP, and
  the IAP-SSH firewall. Depends on `cluster/`.
- `prometheus-pool/`, `core-pool/`, `support-pool/`, `user-pool/` source
  `modules/nodepools`: one private pool each. Depend on `cluster/` for the name
  and on `network/` for ordering (NAT before private nodes).

## Standing one up

```bash
export TG_TF_PATH=tofu
cp -r tofu/clusters/cluster-template tofu/clusters/<cluster-name>
# edit tofu/clusters/<cluster-name>/cluster/terragrunt.hcl: set cluster_name, then uncomment
#   ONE of the two case blocks (dev or redeploy) described below
# edit the pool units: date-stamp pool_name, adjust machine_type for dev
cd tofu/clusters/<cluster-name>
terragrunt run-all plan      # cluster, then network, then the pools
terragrunt run-all apply     # mutates real infra; review the plan first
```

`run-all` walks the `dependency` graph: `cluster/` first, then `network/`, then
the pools. To drive a single unit instead, `cd` into it and run `terragrunt
plan`/`apply` there.

## The two cases

The same config serves two cases, selected in `cluster/terragrunt.hcl`:

- Dev cluster: `create_network = true` (its own VPC), fresh non-colliding ranges,
  smaller node VMs (set per pool), `deletion_protection = false` so CI can tear
  it down.
- Redeploy: `create_network = false` on the existing VPC, reusing the live
  cluster's ranges so the `jupyterhub-home-nfs` allowlist still matches;
  `deletion_protection = true`.

Own VPC per cluster keeps a dev cluster's Cloud NAT and firewall rules from
colliding with prod's. One subnet per cluster, not one per pool: all pools share
the cluster's single pod secondary range.
