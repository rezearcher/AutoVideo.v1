#!/bin/bash

# Get the current project ID
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo "======= DETAILED VERTEX AI GPU QUOTA INCREASE GUIDE ======="
echo "Current project: $PROJECT_ID"
echo "Project number: $PROJECT_NUMBER"
echo ""
echo "Since you're encountering permission issues with the web console, here are multiple ways to request quota increases:"
echo ""

echo "===== OPTION 1: DIRECT CONSOLE URL (RECOMMENDED) ====="
echo "1. Log into the Google Cloud Console with rez.archer@gmail.com (project owner)"
echo "2. Open this direct URL (may work better than our previous attempt):"
echo "   https://console.cloud.google.com/iam-admin/quotas?project=$PROJECT_ID"
echo "3. Filter for 'aiplatform' and 'gpu'"
echo "4. Look for these specific quotas:"
echo "   - custom_model_training_nvidia_t4_gpus"
echo "   - custom_model_training_nvidia_l4_gpus" 
echo "5. Check the boxes and click 'EDIT QUOTAS'"
echo "6. Set both to 1 for region us-central1"
echo ""

echo "===== OPTION 2: QUOTA REQUEST EMAIL ====="
echo "If the console still doesn't work, you can directly email Google Cloud Support:"
echo "1. Send an email to: cloud-support@google.com"
echo "2. Subject: Quota Increase Request for Project $PROJECT_ID"
echo "3. Include in the body:"
echo "   - Project ID: $PROJECT_ID"
echo "   - Project Number: $PROJECT_NUMBER" 
echo "   - Quota: aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus"
echo "   - Region: us-central1"
echo "   - Current Limit: 0"
echo "   - Requested Limit: 1"
echo "   - Justification: Required for video generation in AutoVideo project"
echo "   - Repeat the same for L4 GPUs"
echo ""

echo "===== OPTION 3: CLOUD SUPPORT CONSOLE ====="
echo "1. Visit: https://console.cloud.google.com/support/cases/create?project=$PROJECT_ID"
echo "2. Choose 'Technical Support' → 'Quota'"
echo "3. Fill in details for both GPU types"
echo ""

echo "===== OPTION 4: WORKAROUND UNTIL QUOTA APPROVAL ====="
echo "As a temporary solution, you could modify the code to use CPU-only mode:"
echo "1. Edit vertex_gpu_service.py to force CPU-only mode"
echo "2. This will be slower but would work while waiting for quota approval"
echo ""

echo "Opening direct quota URL in 5 seconds..."
sleep 5
xdg-open "https://console.cloud.google.com/iam-admin/quotas?project=$PROJECT_ID&service=aiplatform.googleapis.com&filter=gpu" 