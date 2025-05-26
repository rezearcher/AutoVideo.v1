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
gcloud iam service-accounts create autovideo-service \
  --display-name="AutoVideo Service Account" \
  --description="Service account for AutoVideo application and monitoring"
```

### 2. Required IAM Roles

The service account needs the following roles:

```bash
# Get your project ID
PROJECT_ID=$(gcloud config get-value project)

# Assign required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com" \
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
  --iam-account=autovideo-service@$PROJECT_ID.iam.gserviceaccount.com

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
  --filter="bindings.members:autovideo-service@$PROJECT_ID.iam.gserviceaccount.com"
```

#### 3. Service Account Key Issues
```
Error: Could not load the default credentials
```
**Solution**: Verify the service account key is properly formatted JSON

### 4. Quota Limits
Some APIs have quotas that might affect monitoring:

- **Monitoring API**: 1000 requests per 100 seconds
- **Logging API**: 60 requests per minute
- **Custom Metrics**: 500 time series per project

Check quotas in the [GCP Console](https://console.cloud.google.com/iam-admin/quotas).

## Cost Considerations

### Monitoring Costs
- **Custom Metrics**: $0.30 per metric per month (first 150 metrics free)
- **Log Ingestion**: $0.50 per GB (first 50 GB free per month)
- **Alert Policies**: Free for first 5 policies, $0.20 per policy after

### Optimization Tips
1. Use log-based metrics instead of custom metrics where possible
2. Set appropriate retention periods for logs
3. Use sampling for high-volume metrics
4. Monitor your billing dashboard regularly

## Security Best Practices

1. **Principle of Least Privilege**: Only grant necessary permissions
2. **Key Rotation**: Rotate service account keys regularly
3. **Audit Logs**: Enable audit logging for monitoring changes
4. **Network Security**: Use VPC if needed for additional isolation

## Next Steps

After completing this setup:

1. ✅ Commit and push your code to trigger the monitoring setup
2. ✅ Check the GitHub Actions workflow execution
3. ✅ Verify monitoring resources in GCP Console
4. ✅ Configure notification channel email addresses
5. ✅ Test alert policies with sample data

## Support

If you encounter issues:

1. Check the [GCP Status Page](https://status.cloud.google.com/)
2. Review GitHub Actions logs for detailed error messages
3. Use `gcloud` CLI with `--verbosity=debug` for detailed output
4. Check the [Cloud Monitoring documentation](https://cloud.google.com/monitoring/docs) 