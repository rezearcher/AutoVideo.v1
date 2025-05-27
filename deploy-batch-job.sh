#!/bin/bash

# Deploy AutoVideo as Cloud Run Job for batch processing
# This is more cost-efficient than GitHub Actions for regular scheduled runs

set -e

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"av-8675309"}
REGION="us-central1"
JOB_NAME="av-video-generator"
IMAGE_NAME="gcr.io/${PROJECT_ID}/av-batch-job"

echo "🚀 Deploying AutoVideo as Cloud Run Job..."
echo "📋 Project: ${PROJECT_ID}"
echo "🌍 Region: ${REGION}"
echo "🏷️ Job: ${JOB_NAME}"

# Build the container image for batch processing
echo "🐳 Building batch processing container..."
docker build -t ${IMAGE_NAME} -f Dockerfile.batch .

# Push to Google Container Registry
echo "📤 Pushing container to GCR..."
docker push ${IMAGE_NAME}

# Deploy as Cloud Run Job
echo "☁️ Deploying Cloud Run Job..."
gcloud run jobs create ${JOB_NAME} \
  --image=${IMAGE_NAME} \
  --region=${REGION} \
  --task-timeout=3600 \
  --max-retries=2 \
  --parallelism=1 \
  --task-count=1 \
  --cpu=2 \
  --memory=4Gi \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --service-account="autovideo-service@${PROJECT_ID}.iam.gserviceaccount.com" \
  --quiet

echo "✅ Cloud Run Job deployed successfully!"
echo ""
echo "📋 Usage:"
echo "  # Run job manually:"
echo "  gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo ""
echo "  # Schedule with Cloud Scheduler:"
echo "  gcloud scheduler jobs create http av-daily-video \\"
echo "    --schedule='0 9 * * *' \\"
echo "    --uri='https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run' \\"
echo "    --http-method=POST \\"
echo "    --oauth-service-account-email='autovideo-service@${PROJECT_ID}.iam.gserviceaccount.com'"
echo ""
echo "💰 Cost Benefits:"
echo "  - Only pay when job runs (~5-10 minutes)"
echo "  - No idle costs"
echo "  - Automatic scaling and retries"
echo "  - Integrated with Google Cloud monitoring" 