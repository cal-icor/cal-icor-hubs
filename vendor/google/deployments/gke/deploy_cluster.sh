#!/bin/bash
set -euo pipefail

# This deploys the Cal-ICOR cluster and core pool in GKE

# Define variables
PROJECT_ID="cal-icor-hubs" # Replace this with your actual GCP project ID
DEPLOYMENT_NAME="cal-icor-cluster-deployment"
CONFIG_PATH="./configs/cluster_config.yaml"

# Set the GCP project context
gcloud config set project "$PROJECT_ID"

# Navigate to the directory where the deploy.sh script is located
cd "$(dirname "$0")"

# Deploy the configuration
gcloud deployment-manager deployments create "$DEPLOYMENT_NAME" --config "$CONFIG_PATH" || \
gcloud deployment-manager deployments update "$DEPLOYMENT_NAME" --config "$CONFIG_PATH"

# To manually delete the deployment, run the following command:
# gcloud deployment-manager deployments delete "$DEPLOYMENT_NAME"

echo "Deployment process completed."
