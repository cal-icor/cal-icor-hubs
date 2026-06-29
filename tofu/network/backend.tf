terraform {
  backend "gcs" {
    bucket = "cal-icor-hubs-tofu-state"
    prefix = "spring-2025/network"
  }
}
