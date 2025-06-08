#!/bin/bash
#
# Setup script for monitoring permissions
# - Adds monitoring viewer role to service accounts for quota checking
# - Verifies GCP project configuration
#

set -e

# Default values
PROJECT_ID=${GCP_PROJECT:-$(gcloud config get-value project)}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Check if project ID is set
if [ -z "$PROJECT_ID" ]; then
  echo -e "${RED}Error: No GCP project ID specified.${NC}"
  echo "Set the GCP_PROJECT environment variable or run 'gcloud config set project <PROJECT_ID>'"
  exit 1
fi

echo -e "${GREEN}Setting up monitoring permissions for project: ${PROJECT_ID}${NC}"

# Get the default compute service account
COMPUTE_SA="$(gcloud iam service-accounts list --filter="name:compute" --format="value(email)" --project="${PROJECT_ID}")"

if [ -z "$COMPUTE_SA" ]; then
  echo -e "${YELLOW}Warning: Default compute service account not found${NC}"
  echo "Creating service account for Cloud Run deployments"
  
  # Create a new service account
  gcloud iam service-accounts create "cloud-run-deploy" \
    --display-name="Cloud Run Deployment Service Account" \
    --project="${PROJECT_ID}"
    
  COMPUTE_SA="cloud-run-deploy@${PROJECT_ID}.iam.gserviceaccount.com"
  
  echo -e "${GREEN}Created service account: ${COMPUTE_SA}${NC}"
fi

echo -e "${GREEN}Using service account: ${COMPUTE_SA}${NC}"

# Grant monitoring viewer role to the service account for quota checking
echo "Adding monitoring viewer role to service account..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/monitoring.viewer"

echo -e "${GREEN}✅ Monitoring viewer role added to ${COMPUTE_SA}${NC}"
echo "This allows the service to check Veo API quota and token usage at runtime."

# Check if Monitoring API is enabled
echo "Checking if Monitoring API is enabled..."
if gcloud services list --project="${PROJECT_ID}" | grep -q "monitoring.googleapis.com"; then
  echo -e "${GREEN}✅ Monitoring API is already enabled${NC}"
else
  echo "Enabling Monitoring API..."
  gcloud services enable monitoring.googleapis.com --project="${PROJECT_ID}"
  echo -e "${GREEN}✅ Monitoring API enabled${NC}"
fi

echo -e "\n${GREEN}=== Monitoring Permissions Setup Complete ===${NC}"
echo "Your service account now has monitoring access for quota checking."
echo -e "\nNext steps:"
echo "1. You can now use the gcloud monitoring time-series API to check Veo token usage"
echo "2. Deploy the smoke test and service with your CI/CD pipeline"
echo "3. Consider requesting a quota increase for Veo API if needed:"
echo "   - Go to console.cloud.google.com/iam-admin/quotas"
echo "   - Filter for 'Generative Video Tokens'"
echo "   - Request increase to 500/minute and 20,000/day if needed"

echo -e "\n${GREEN}Done!${NC}" 