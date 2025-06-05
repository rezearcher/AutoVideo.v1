#!/bin/bash
set -e

# Configuration
PROJECT_ID="av-8675309"
IMAGE_NAME="av-gpu-diagnostic"
TAG="latest"

# Create fonts directory if it doesn't exist
mkdir -p fonts

# Download sample fonts if not present
if [ ! -f fonts/DejaVuSans.ttf ]; then
    echo "Downloading sample fonts..."
    wget -O fonts/DejaVuSans.ttf https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf
fi

# Build the container
echo "Building diagnostic container..."
docker build -t gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${TAG} -f Dockerfile.gpu-diagnostic .

# Push to GCR
echo "Pushing to Google Container Registry..."
docker push gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${TAG}

echo "Creating Vertex AI job spec..."
cat > diagnostic_job.json << EOL
{
  "displayName": "gpu-diagnostic-test",
  "jobSpec": {
    "workerPoolSpecs": [
      {
        "machineSpec": {
          "machineType": "n1-standard-4",
          "acceleratorType": "NVIDIA_TESLA_T4",
          "acceleratorCount": 1
        },
        "replicaCount": 1,
        "containerSpec": {
          "imageUri": "gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${TAG}",
          "command": [],
          "args": ["--test-encode", "--output", "/tmp/diagnostic_results.json"]
        }
      }
    ]
  }
}
EOL

echo "Done! To run the diagnostic job in Vertex AI, use:"
echo "gcloud ai custom-jobs create --region=us-central1 --config=diagnostic_job.json"
echo ""
echo "To monitor logs:"
echo "gcloud ai custom-jobs stream-logs --region=us-central1 JOB_ID"
echo ""
echo "To create a CPU-only version (for comparison):"
echo "sed -i 's/\"acceleratorType\": \"NVIDIA_TESLA_T4\",//g' diagnostic_job.json"
echo "sed -i 's/\"acceleratorCount\": 1,//g' diagnostic_job.json"
echo "gcloud ai custom-jobs create --region=us-central1 --config=diagnostic_job.json" 