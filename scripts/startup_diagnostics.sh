#!/bin/bash
# Startup diagnostics for AutoVideo - tests network connectivity to Google APIs

echo "🚀 AutoVideo Startup Diagnostics"
echo "================================="

# Test basic connectivity
echo "🌐 Testing network connectivity..."

# Test DNS resolution
echo "🔍 Testing DNS resolution..."
for endpoint in "us-central1-aiplatform.googleapis.com" "aiplatform.googleapis.com" "googleapis.com"; do
    echo -n "  Testing $endpoint: "
    if nslookup "$endpoint" > /dev/null 2>&1; then
        echo "✅ DNS OK"
    else
        echo "❌ DNS FAILED"
    fi
done

# Test HTTP connectivity to Google APIs
echo "🔗 Testing HTTP connectivity..."
for endpoint in "https://aiplatform.googleapis.com" "https://storage.googleapis.com"; do
    echo -n "  Testing $endpoint: "
    if curl -s --max-time 10 "$endpoint" > /dev/null 2>&1; then
        echo "✅ HTTP OK"
    else
        echo "❌ HTTP FAILED"
    fi
done

# Test specific Vertex AI endpoint
echo "🎯 Testing Vertex AI regional endpoint..."
endpoint="https://us-central1-aiplatform.googleapis.com"
echo -n "  Testing $endpoint: "
if curl -s --max-time 10 "$endpoint" > /dev/null 2>&1; then
    echo "✅ VERTEX AI OK"
else
    echo "❌ VERTEX AI FAILED"
fi

# Test Google metadata server (for service account auth)
echo "🔐 Testing metadata server..."
echo -n "  Testing metadata.google.internal: "
if curl -s --max-time 5 -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" > /dev/null 2>&1; then
    echo "✅ METADATA OK"
else
    echo "❌ METADATA FAILED"
fi

echo "================================="
echo "🎬 Starting main application..." 