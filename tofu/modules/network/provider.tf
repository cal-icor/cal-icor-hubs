provider "google" {
  project = var.project
  region  = var.region

  # Billing label applied to every labelable resource in this module. The router,
  # NAT, and firewall rules cannot carry labels in GCP, so this lands on the
  # reserved egress IP (the one labelable network resource here). The repo uses
  # the "hub" key as the single billing dimension for human-readable rollups
  # (real hub names, plus "support" / "core" for shared services); "networking"
  # is a new value for shared network plumbing.
  default_labels = {
    hub = "networking"
  }
}
