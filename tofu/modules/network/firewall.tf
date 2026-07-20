# IAP TCP forwarding for SSH to private nodes.
#
# Private nodes have no external IP, so plain `gcloud compute ssh <node>` cannot
# reach them. IAP TCP forwarding (`--tunnel-through-iap`) tunnels SSH from
# Google's IAP range to the node's internal IP. This rule permits that range to
# reach tcp:22 on the cluster nodes (target tag hub-cluster, which every pool in
# this cluster carries).
#
# Scoped to the IAP range and the node tag, so SSH access control lives at the
# IAP access-level layer rather than in firewall source-IP edits.
resource "google_compute_firewall" "iap_ssh" {
  name      = var.iap_ssh_firewall_name
  network   = var.network
  direction = "INGRESS"

  # IAP-tunneled SSH always arrives from this range, never the operator's
  # workstation IP, so access control lives at the IAP layer, not in this rule.
  source_ranges = [var.iap_source_range]
  target_tags   = [var.node_tag]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
