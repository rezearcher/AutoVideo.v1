#!/bin/bash

# Get the current project ID
PROJECT_ID=$(gcloud config get-value project)

echo "======= DIRECT QUOTA INCREASE LINKS ======="
echo "Current project: $PROJECT_ID"
echo ""
echo "The following links should take you directly to the edit quota pages:"
echo ""

echo "===== LINK FOR T4 GPU QUOTA ====="
echo "https://console.cloud.google.com/iam-admin/quotas/metric?project=$PROJECT_ID&service=aiplatform.googleapis.com&metric=aiplatform.googleapis.com%2Fcustom_model_training_nvidia_t4_gpus"
echo ""
echo "Opening T4 GPU quota page in 5 seconds..."
sleep 5
xdg-open "https://console.cloud.google.com/iam-admin/quotas/metric?project=$PROJECT_ID&service=aiplatform.googleapis.com&metric=aiplatform.googleapis.com%2Fcustom_model_training_nvidia_t4_gpus"

echo ""
echo "===== LINK FOR L4 GPU QUOTA ====="
echo "https://console.cloud.google.com/iam-admin/quotas/metric?project=$PROJECT_ID&service=aiplatform.googleapis.com&metric=aiplatform.googleapis.com%2Fcustom_model_training_nvidia_l4_gpus"
echo ""
echo "Opening L4 GPU quota page in 10 seconds..."
sleep 10
xdg-open "https://console.cloud.google.com/iam-admin/quotas/metric?project=$PROJECT_ID&service=aiplatform.googleapis.com&metric=aiplatform.googleapis.com%2Fcustom_model_training_nvidia_l4_gpus"

echo ""
echo "If these don't work directly, try this alternative approach:"
echo "1. Go to: https://console.cloud.google.com/apis/api/aiplatform.googleapis.com/quotas?project=$PROJECT_ID"
echo "2. Look for GPU quotas in the list and click 'Edit Quotas' next to them"
echo ""
echo "Opening alternative API quotas page in 15 seconds..."
sleep 15
xdg-open "https://console.cloud.google.com/apis/api/aiplatform.googleapis.com/quotas?project=$PROJECT_ID" 