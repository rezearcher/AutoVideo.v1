#!/bin/bash

# AutoVideo GCP Setup Script
# This script sets up all required GCP resources for AutoVideo monitoring and deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI is not installed. Please install it first:"
    echo "https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get current project
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
    print_error "No GCP project is set. Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

print_status "Setting up AutoVideo for project: $PROJECT_ID"

# Enable required APIs
print_status "Enabling required Google Cloud APIs..."

REQUIRED_APIS=(
    "cloudbuild.googleapis.com"
    "run.googleapis.com"
    "containerregistry.googleapis.com"
    "monitoring.googleapis.com"
    "logging.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "serviceusage.googleapis.com"
    "iam.googleapis.com"
    "cloudtrace.googleapis.com"
    "clouderrorreporting.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    print_status "Enabling $api..."
    if gcloud services enable "$api" --quiet; then
        print_success "✓ $api enabled"
    else
        print_error "Failed to enable $api"
        exit 1
    fi
done

# Create service account
SERVICE_ACCOUNT_NAME="autovideo-service"
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

print_status "Creating service account: $SERVICE_ACCOUNT_NAME"

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &>/dev/null; then
    print_warning "Service account $SERVICE_ACCOUNT_NAME already exists"
else
    if gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="AutoVideo Service Account" \
        --description="Service account for AutoVideo application and monitoring"; then
        print_success "✓ Service account created"
    else
        print_error "Failed to create service account"
        exit 1
    fi
fi

# Assign required roles
print_status "Assigning IAM roles to service account..."

REQUIRED_ROLES=(
    "roles/run.admin"
    "roles/monitoring.admin"
    "roles/logging.admin"
    "roles/storage.admin"
    "roles/cloudbuild.builds.editor"
    "roles/iam.serviceAccountUser"
)

for role in "${REQUIRED_ROLES[@]}"; do
    print_status "Assigning role: $role"
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$role" \
        --quiet; then
        print_success "✓ $role assigned"
    else
        print_warning "Failed to assign $role (may already exist)"
    fi
done

# Generate service account key
KEY_FILE="autovideo-key.json"
print_status "Generating service account key..."

if [ -f "$KEY_FILE" ]; then
    print_warning "Key file $KEY_FILE already exists. Backing up..."
    mv "$KEY_FILE" "${KEY_FILE}.backup.$(date +%s)"
fi

if gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SERVICE_ACCOUNT_EMAIL"; then
    print_success "✓ Service account key generated: $KEY_FILE"
else
    print_error "Failed to generate service account key"
    exit 1
fi

# Verify setup
print_status "Verifying setup..."

# Check APIs
print_status "Checking enabled APIs..."
ENABLED_COUNT=0
for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
        ENABLED_COUNT=$((ENABLED_COUNT + 1))
    else
        print_warning "API $api is not enabled"
    fi
done

print_success "✓ $ENABLED_COUNT/${#REQUIRED_APIS[@]} APIs enabled"

# Check service account
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &>/dev/null; then
    print_success "✓ Service account exists and is accessible"
else
    print_error "Service account verification failed"
fi

# Test monitoring access
print_status "Testing monitoring API access..."
if gcloud alpha monitoring policies list --limit=1 &>/dev/null; then
    print_success "✓ Monitoring API access verified"
else
    print_warning "Monitoring API access test failed (this may be normal if no policies exist yet)"
fi

# Display next steps
echo ""
print_success "🎉 GCP setup completed successfully!"
echo ""
print_status "Next steps:"
echo "1. Add the following secrets to your GitHub repository:"
echo "   - GOOGLE_CLOUD_PROJECT_ID: $PROJECT_ID"
echo "   - GOOGLE_CLOUD_SA_KEY: (contents of $KEY_FILE)"
echo ""
echo "2. To view the service account key for GitHub Secrets:"
echo "   cat $KEY_FILE"
echo ""
echo "3. GitHub repository settings:"
echo "   Go to: Settings → Secrets and variables → Actions"
echo "   Add the secrets listed above"
echo ""
echo "4. Additional API keys needed (add to GitHub Secrets):"
echo "   - OPENAI_API_KEY"
echo "   - ELEVENLABS_API_KEY"
echo "   - YOUTUBE_CLIENT_ID"
echo "   - YOUTUBE_CLIENT_SECRET"
echo "   - YOUTUBE_PROJECT_ID"
echo ""

# Security reminder
print_warning "🔒 Security reminder:"
echo "   - Keep the service account key ($KEY_FILE) secure"
echo "   - Do not commit it to your repository"
echo "   - Consider rotating keys regularly"
echo "   - Delete the local key file after adding to GitHub Secrets"

# Cost information
echo ""
print_status "💰 Cost information:"
echo "   - Most monitoring features are free within limits"
echo "   - Custom metrics: First 150 free, then \$0.30/metric/month"
echo "   - Log ingestion: First 50GB free, then \$0.50/GB"
echo "   - Monitor your usage in the GCP Console"

echo ""
print_success "Setup complete! You can now commit and push your code to trigger deployment." 