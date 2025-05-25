#!/bin/bash

# Exit on error
set -e

# Get the current timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Get the project ID
PROJECT_ID=$(gcloud config get-value project)

# Build and push the container with timestamp
echo "Building and pushing container..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/av-app:$TIMESTAMP

# Deploy to Cloud Run with no-traffic tag
echo "Deploying to Cloud Run..."
gcloud run deploy av-app \
  --image gcr.io/$PROJECT_ID/av-app:$TIMESTAMP \
  --platform managed \
  --region us-central1 \
  --no-traffic \
  --tag latest

# Wait for deployment to complete
echo "Waiting for deployment to complete..."
sleep 30

# Move all traffic to the new revision
echo "Moving traffic to new revision..."
gcloud run services update-traffic av-app \
  --to-latest \
  --region us-central1

echo "Deployment complete!" 