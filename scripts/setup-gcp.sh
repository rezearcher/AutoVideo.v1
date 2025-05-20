#!/bin/bash

# Exit on error
set -e

# Load environment variables
source .env

# Create GitHub environments
echo "Creating GitHub environments..."
gh api repos/:owner/:repo/environments -f name=staging -f wait_timer=0
gh api repos/:owner/:repo/environments -f name=production -f wait_timer=0

# Apply Cloud Storage configuration
echo "Deploying Cloud Storage configuration..."
gcloud deployment-manager deployments create av-storage --config cloud-storage-config.yaml

# Update service account permissions
echo "Updating service account permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@av-8675309.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@av-8675309.iam.gserviceaccount.com" \
    --role="roles/run.admin"

echo "Setup completed successfully!" 