#!/bin/bash
# Deploy with Veo AI enabled

# Configuration
SERVICE="av-app"
REGION="us-central1"
PROJECT_ID=$(gcloud config get-value project)
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE}:latest"

# Build the Docker image
echo "Building Docker image ${IMAGE_NAME}..."
docker build -t ${IMAGE_NAME} .
docker push ${IMAGE_NAME}

# Deploy to Cloud Run
echo "Deploying to Cloud Run with Veo enabled..."
gcloud run deploy ${SERVICE} \
  --image ${IMAGE_NAME} \
  --region ${REGION} \
  --platform managed \
  --memory 8Gi \
  --cpu 4 \
  --concurrency 10 \
  --timeout 3600 \
  --min-instances 1 \
  --set-env-vars="VEO_ENABLED=true,VERTEX_BUCKET_NAME=av-8675309-video-jobs"

echo "Deployment complete! The service is now running with Veo AI enabled."
echo "URL: $(gcloud run services describe ${SERVICE} --region ${REGION} --format='value(status.url)')" 