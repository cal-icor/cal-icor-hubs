# IAP TCP forwarding for SSH to private nodes.
#
# Once nodes lose their external IPs in the later migration phases, plain
# `gcloud compute ssh <node>` can no longer reach them. IAP TCP forwarding
# (`--tunnel-through-iap`) tunnels SSH from Google's IAP range to the node's
# internal IP instead. This rule permits that range to reach tcp:22 on the
# cluster nodes (target tag hub-cluster, which every pool in this cluster
# carries).
#
# Scoped deliberately to the IAP range and the node tag. The pre-existing broad
# `allow-ssh` rule (tcp:22 from 0.0.0.0/0, all instances) currently covers this
# path too, but that rule is slated to be narrowed or removed in the access
# lock-down stage. A dedicated, tightly scoped IAP rule means SSH-over-IAP
# survives that lock-down.
resource "google_compute_firewall" "iap_ssh" {
  name      = var.iap_ssh_firewall_name
  network   = var.network
  direction = "INGRESS"

  # IAP-tunneled SSH always arrives from this range, never the operator's
  # workstation IP, so source-IP lock-down later happens at the IAP access-level
  # layer, not by editing this rule.
  source_ranges = [var.iap_source_range]
  target_tags   = [var.node_tag]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
