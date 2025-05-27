#!/bin/bash

# Build and Push GPU Container for Vertex AI
set -e

# Configuration
PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
REGION=${REGION:-us-central1}
IMAGE_NAME="av-gpu-job"
CONTAINER_IMAGE="gcr.io/$PROJECT_ID/$IMAGE_NAME"

echo "🚀 Building GPU container for Vertex AI..."
echo "Project ID: $PROJECT_ID"
echo "Image: $CONTAINER_IMAGE"

# Enable required APIs
echo "📋 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable storage.googleapis.com

# Configure Docker to use gcloud as a credential helper
echo "🔐 Configuring Docker authentication..."
gcloud auth configure-docker

# Build and push container
echo "🔨 Building container..."
docker build -t $CONTAINER_IMAGE -f Dockerfile.gpu .

echo "📤 Pushing container..."
docker push $CONTAINER_IMAGE

echo "✅ Container built and pushed successfully!"
echo "Image: $CONTAINER_IMAGE"

# Create GCS bucket for jobs if it doesn't exist
BUCKET_NAME="$PROJECT_ID-video-jobs"
echo "📦 Creating GCS bucket: $BUCKET_NAME"
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://$BUCKET_NAME/ 2>/dev/null || echo "Bucket already exists"

echo "🎯 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Test the container: gcloud ai custom-jobs create --region=$REGION --display-name=test-gpu-job --worker-pool-spec=machine-type=n1-standard-4,replica-count=1,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=1,container-image-uri=$CONTAINER_IMAGE"
echo "2. Update your main app to use the VertexGPUJobService"
echo "" 