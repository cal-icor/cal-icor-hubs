output "bucket_name" {
  value       = google_storage_bucket.state.name
  description = "Name of the remote-state bucket."
}

output "bucket_url" {
  value       = google_storage_bucket.state.url
  description = "gs:// URL of the remote-state bucket."
}
