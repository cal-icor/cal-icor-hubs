#!/bin/bash
set -euo pipefail

# Define variables
PROJECT_ID="cal-icor-hubs" # Replace this with your actual GCP project ID
DEPLOYMENT_NAME="user-pool-deployment"
CONFIG_PATH="./configs/user_pool.yaml"

# Set the GCP project context
gcloud config set project "$PROJECT_ID"

# Navigate to the directory where the script is located
cd "$(dirname "$0")"

# Deploy the node pool configuration
gcloud deployment-manager deployments create "$DEPLOYMENT_NAME" --config "$CONFIG_PATH" || \
gcloud deployment-manager deployments update "$DEPLOYMENT_NAME" --config "$CONFIG_PATH"

# To manually delete the deployment, run the following command:
# gcloud deployment-manager deployments delete "$DEPLOYMENT_NAME"

echo "Node pool deployment process completed."
