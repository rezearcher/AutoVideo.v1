#!/bin/bash

# Setup VM management permissions for Cloud Run service
# This enables the fast render fallback functionality

set -e

PROJECT_ID=${1:-"av-8675309"}
SERVICE_ACCOUNT="github-actions@${PROJECT_ID}.iam.gserviceaccount.com"
CLOUDRUN_SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"

echo "🔧 Setting up VM management permissions for AutoVideo..."
echo "Project: $PROJECT_ID"
echo "GitHub Actions SA: $SERVICE_ACCOUNT"
echo "Cloud Run SA: $CLOUDRUN_SERVICE_ACCOUNT"

# Ensure Cloud Run service account has necessary permissions
echo "📝 Granting Compute Engine permissions to Cloud Run service account..."

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CLOUDRUN_SERVICE_ACCOUNT" \
  --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CLOUDRUN_SERVICE_ACCOUNT" \
  --role="roles/compute.securityAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CLOUDRUN_SERVICE_ACCOUNT" \
  --role="roles/iam.serviceAccountUser"

# Enable Compute Engine API if not already enabled
echo "🔌 Enabling Compute Engine API..."
gcloud services enable compute.googleapis.com --project=$PROJECT_ID

# Create staging and output buckets if they don't exist
echo "📦 Setting up storage buckets..."

STAGING_BUCKET="${PROJECT_ID}-staging"
OUTPUT_BUCKET="${PROJECT_ID}-outputs"

gsutil mb -p $PROJECT_ID -c STANDARD -l us-central1 gs://$STAGING_BUCKET/ 2>/dev/null || echo "✅ Staging bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l us-central1 gs://$OUTPUT_BUCKET/ 2>/dev/null || echo "✅ Output bucket already exists"

# Set bucket permissions
echo "🔒 Setting bucket permissions..."

gsutil iam ch serviceAccount:$CLOUDRUN_SERVICE_ACCOUNT:objectAdmin gs://$STAGING_BUCKET
gsutil iam ch serviceAccount:$CLOUDRUN_SERVICE_ACCOUNT:objectAdmin gs://$OUTPUT_BUCKET

# Create firewall rule for VM communication (if needed)
echo "🛡️ Setting up firewall rules..."
gcloud compute firewall-rules create autovideo-render-allow-internal \
  --allow tcp:8080,tcp:22 \
  --source-ranges 10.0.0.0/8 \
  --target-tags autovideo-render \
  --description "Allow internal communication for AutoVideo render VMs" \
  --project $PROJECT_ID 2>/dev/null || echo "✅ Firewall rule already exists"

echo "✅ VM management permissions setup complete!"
echo ""
echo "🎯 Fast render fallback is now enabled:"
echo "  - Cloud Run can create/manage Compute Engine VMs"
echo "  - Storage buckets configured for asset staging"
echo "  - Firewall rules allow VM communication"
echo ""
echo "🚀 The AutoVideo system will now automatically fall back to VM rendering"
echo "   when Vertex AI experiences timeouts or quota issues." 