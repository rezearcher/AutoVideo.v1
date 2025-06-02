#!/bin/bash

# Get the current project ID
PROJECT_ID=$(gcloud config get-value project)

# Print instructions
echo "======= VERTEX AI GPU QUOTA INCREASE GUIDE ======="
echo "Current project: $PROJECT_ID"
echo ""
echo "You need to increase your Vertex AI GPU quotas to enable video processing."
echo ""
echo "1. Opening the Google Cloud Console Quotas page in your browser."
echo "2. Look for these metrics to increase:"
echo "   - aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus"
echo "   - aiplatform.googleapis.com/custom_model_training_nvidia_l4_gpus"
echo ""
echo "3. Request quota values of at least 1 for each in us-central1 region."
echo "4. Justification to use: 'Required for video generation in AutoVideo project'"
echo ""
echo "The page will open in your default browser in 5 seconds..."
sleep 5

# Open the quotas page
xdg-open "https://console.cloud.google.com/iam-admin/quotas?project=$PROJECT_ID&service=aiplatform.googleapis.com&filter=gpu" 