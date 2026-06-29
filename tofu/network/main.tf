# Phase A of the public-to-private node migration: outbound egress for private nodes.
#
# Direction matters here. This file only creates an OUTBOUND path. It does not
# touch the INBOUND ingress IP 34.56.76.244 (reserved address
# wildcard-dns-target-spring-2025, pinned to the ingress-nginx LoadBalancer via
# support/values.yaml loadBalancerIP, resolved by the Infoblox wildcard
# *.jupyter.cal-icor.org). That ingress IP and the NAT egress IP below are
# separate addresses serving opposite directions and must stay separate.

# Reserved static egress IP. Stable, known source address for all private-node
# traffic leaving for the public internet (quay.io, ghcr.io, Docker Hub, PyPI,
# conda, apt, ACME). Reserved (not AUTO) so it can be documented and allowlisted
# downstream the same way the inbound IP is.
resource "google_compute_address" "nat_egress" {
  name         = var.nat_egress_ip_name
  address_type = "EXTERNAL"
  region       = var.region
}

resource "google_compute_router" "nat_router" {
  name    = var.router_name
  region  = var.region
  network = var.network
}

resource "google_compute_router_nat" "nat" {
  name   = var.nat_name
  router = google_compute_router.nat_router.name
  region = var.region

  nat_ip_allocate_option = "MANUAL_ONLY"
  nat_ips                = [google_compute_address.nat_egress.self_link]

  # NAT every subnet range in the region, including the GKE pod secondary range
  # (10.92.0.0/14). Pod egress is the whole reason NAT is needed, so it must be
  # covered, not just the node primary IPs.
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  # A multi-tenant JupyterHub node packs many pods making outbound connections.
  # Dynamic port allocation prevents source-port exhaustion that would show up as
  # intermittent egress failures. Endpoint-independent mapping must be off for
  # dynamic allocation.
  enable_dynamic_port_allocation      = true
  enable_endpoint_independent_mapping = false
  min_ports_per_vm                    = 64
  max_ports_per_vm                    = 2048

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
