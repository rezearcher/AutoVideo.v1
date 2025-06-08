#!/bin/bash
# Smoke test for Veo-only pipeline deployment

set -e

# Get the API URL from environment or use default
API_URL=${API_URL:-"https://av-app-939407899550.us-central1.run.app"}

echo "🔍 Running smoke test against API: $API_URL"

# Step 1: Generate auth token
echo "🔑 Generating authentication token..."
TOKEN=$(gcloud auth print-identity-token)

# Step 2: Send generation request
echo "🚀 Sending video generation request..."
RESPONSE=$(curl -s -X POST "$API_URL/generate" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"topic":"Neon samurai crossing rainy street","use_veo":true}')

echo "✅ Generation started: $RESPONSE"

# Step 3: Monitor status
echo "⏳ Monitoring generation status (checking every 5s)..."
echo "   Expected phases: story_generation → veo_scene_1/x → ... → veo_scene_x/x → stitching → upload_complete"

watch -n 5 "curl -s -H 'Authorization: Bearer $TOKEN' $API_URL/status | jq ." 