# The GCS bucket holding every unit's remote state, including its own.
# Adopted via import, never created.
resource "google_storage_bucket" "state" {
  name     = var.bucket_name
  location = var.location

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = var.soft_delete_retention_seconds
  }

  labels = var.labels

  # Guards the bucket that stores all state, including this unit's own.
  lifecycle {
    prevent_destroy = true
  }
}
