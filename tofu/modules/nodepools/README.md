# tofu/modules/nodepools: private GKE node pools for spring-2025

A reusable module that creates one **private** node pool on the `spring-2025`
cluster — nodes get internal IPs only, so their outbound traffic flows through
the Cloud NAT created by [`modules/network`](../network).

## How it fits the migration

The public-to-private migration is build-alongside, not in-place:

1. A unit under `tofu/spring-2025/<role>-pool/` calls this module to create a new
   private pool next to the existing public one.
2. The old pool is cordoned and drained onto the new one.
3. The old (public) pool is deleted once the new one is validated.

So this module only ever **creates** a pool. It never imports or mutates the
existing public pools, which are not tofu-managed.

Config is meant to mirror the pool being replaced exactly. For a given pool the
only intended differences from its public predecessor are:

- `enable_private_nodes = true`
- a date-stamped `pool_name` (house style `<role>-pool-YYYY-MM-DD`)

`pool_name` is also written as the `hub.jupyter.org/pool-name` node label, which
is the value helm `nodeSelector`s pin. Read `pool_name_selector` from the outputs
to get the exact `key=value` to update in the paired helm change before draining.

## Zone pinning

`node_locations` must be the single zone where the pool's stateful PD lives
(`us-central1-b` for both prometheus-data and the NFS disk) so pods can reattach
their disks after moving pools.

## Provider and versions

This module ships no `provider.tf` or `versions.tf`; Terragrunt generates them
from `tofu/root.hcl`. Run it through a unit, not directly.

<!-- BEGIN_TF_DOCS -->
<!-- END_TF_DOCS -->
