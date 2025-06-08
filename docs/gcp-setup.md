# Google Cloud Platform Setup Guide

This guide covers all the GCP configuration required for AutoVideo monitoring and deployment.

## Required APIs

The following APIs must be enabled in your Google Cloud Project:

### Core APIs (Required)
```bash
# Enable all required APIs at once
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com
```

### Individual API Descriptions

| API | Service Name | Purpose |
|-----|--------------|---------|
| **Cloud Build** | `cloudbuild.googleapis.com` | Building Docker containers in CI/CD |
| **Cloud Run** | `run.googleapis.com` | Hosting the application |
| **Container Registry** | `containerregistry.googleapis.com` | Storing Docker images |
| **Cloud Monitoring** | `monitoring.googleapis.com` | Custom metrics and alerting |
| **Cloud Logging** | `logging.googleapis.com` | Application logs and log-based metrics |
| **Resource Manager** | `cloudresourcemanager.googleapis.com` | Project-level operations |
| **Service Usage** | `serviceusage.googleapis.com` | Managing API enablement |
| **Identity & Access Management** | `iam.googleapis.com` | Service account management |

## Service Account Setup

### 1. Create Service Account

```bash
# Create service account for AutoVideo
gcloud iam service-accounts create av-service \
  --display-name="AutoVideo Service Account" \
  --description="Service account for AutoVideo application and monitoring"
```

### 2. Required IAM Roles

The service account needs the following roles:

```bash
# Get your project ID
PROJECT_ID="av-8675309"

# Assign required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:av-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### 3. Role Descriptions

| Role | Purpose |
|------|---------|
| `roles/run.admin` | Deploy and manage Cloud Run services |
| `roles/monitoring.admin` | Create and manage monitoring resources |
| `roles/logging.admin` | Create log-based metrics and manage logs |
| `roles/storage.admin` | Access Cloud Storage for artifacts |
| `roles/cloudbuild.builds.editor` | Trigger and manage builds |
| `roles/iam.serviceAccountUser` | Use service accounts for deployment |

### 4. Generate Service Account Key

```bash
# Generate and download service account key
gcloud iam service-accounts keys create autovideo-key.json \
  --iam-account=av-service@$PROJECT_ID.iam.gserviceaccount.com

# Display the key content for GitHub Secrets
cat autovideo-key.json
```

## GitHub Secrets Configuration

Add the following secrets to your GitHub repository:

### Required Secrets

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `GOOGLE_CLOUD_PROJECT_ID` | Your GCP Project ID | Project identifier |
| `GOOGLE_CLOUD_SA_KEY` | Contents of `autovideo-key.json` | Service account credentials |
| `OPENAI_API_KEY` | Your OpenAI API key | For story generation |
| `ELEVENLABS_API_KEY` | Your ElevenLabs API key | For voice synthesis |
| `YOUTUBE_CLIENT_ID` | YouTube API client ID | For video uploads |
| `YOUTUBE_CLIENT_SECRET` | YouTube API client secret | For video uploads |
| `YOUTUBE_PROJECT_ID` | YouTube API project ID | For video uploads |

### Setting GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret with the corresponding value

## Monitoring-Specific Setup

### 1. Enable Monitoring APIs

```bash
# Enable monitoring-specific APIs
gcloud services enable \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  clouderrorreporting.googleapis.com
```

### 2. Create Notification Channels

The monitoring setup script will create notification channels, but you can also create them manually:

```bash
# Create email notification channel
gcloud alpha monitoring channels create \
  --display-name="AutoVideo Email Alerts" \
  --type=email \
  --channel-labels=email_address=your-email@example.com
```

### 3. Verify Monitoring Setup

```bash
# Check if monitoring APIs are enabled
gcloud services list --enabled --filter="name:monitoring"

# List existing alert policies
gcloud alpha monitoring policies list

# List custom metrics
gcloud logging metrics list
```

## Verification Commands

Run these commands to verify your setup:

### 1. Check API Status
```bash
# Verify all required APIs are enabled
gcloud services list --enabled --filter="name:(monitoring|logging|run|cloudbuild)"
```

### 2. Test Service Account
```bash
# Test service account permissions
gcloud auth activate-service-account --key-file=autovideo-key.json
gcloud projects describe $PROJECT_ID
```

### 3. Test Monitoring Access
```bash
# Test monitoring API access
gcloud alpha monitoring policies list --limit=1
```

## Troubleshooting

### Common Issues

#### 1. API Not Enabled Error
```
Error: API [monitoring.googleapis.com] not enabled
```
**Solution**: Enable the required API
```bash
gcloud services enable monitoring.googleapis.com
```

#### 2. Permission Denied Error
```
Error: Permission denied on resource project
```
**Solution**: Check service account roles
```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:av-service@$PROJECT_ID.iam.gserviceaccount.com"
```

#### 3. Service Account Key Issues
```