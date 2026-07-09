# Cluster identity for the spring-2025 units. Read by every unit in this folder
# via read_terragrunt_config(find_in_parent_folders("cluster.hcl")), so the
# cluster name lives in exactly one place. Units derive their resource names from
# cluster_name (e.g. "${cluster_name}-nat-router"), matching what cluster-template
# derives from dependency.cluster.outputs.name.
#
# spring-2025 is a pre-existing cluster, not created by a tofu cluster/ unit, so
# its name is declared here rather than taken from a cluster output.
locals {
  cluster_name = "spring-2025"
  network      = "default"
}
