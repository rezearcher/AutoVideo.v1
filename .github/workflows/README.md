# AutoVideo GitHub Actions Workflows

This directory contains the GitHub Actions workflows for the AutoVideo platform.

## 🚀 Current Active Workflows

### 1. `ci.yml` - CI Pipeline
**Triggers:** Push to main/develop, Pull Requests
**Purpose:** Code quality and testing
- **Jobs:**
  - `test` - Run unit tests with coverage
  - `lint` - Code formatting (Black, isort, flake8)
  - `security` - Security scanning (Bandit, Safety)
  - `integration-test` - Integration tests with GCP

### 2. `deploy.yml` - Unified Deployment Pipeline ⭐ **NEW**
**Triggers:** Push to main, Manual dispatch
**Purpose:** Complete platform deployment
- **Jobs:**
  - `validate` - Pre-deployment validation and change detection
  - `test` - Run API tests before deployment
  - `deploy-gpu-container` - Deploy Vertex AI GPU container (parallel)
  - `deploy-main-app` - Deploy main app to Cloud Run (parallel)
  - `setup-monitoring` - Configure Google Cloud Monitoring
  - `verify-deployment` - Post-deployment health checks
  - `cleanup-on-failure` - Automatic rollback on failure

### 3. `scheduled-generation.yml` - Daily Video Generation
**Triggers:** Daily cron schedule (9 AM EST), Manual dispatch
**Purpose:** Automated video generation and upload

## 🔄 Workflow Improvements

### **Before (4 separate workflows):**
- `main.yml` - Main app deployment
- `deploy-vertex-gpu.yml` - GPU container deployment
- `setup-monitoring.yml` - Monitoring setup
- `ci.yml` - CI pipeline

### **After (2 main workflows):**
- `ci.yml` - CI pipeline (unchanged)
- `deploy.yml` - **Unified deployment** (combines 3 workflows)

## ✨ Key Features of the New Unified Deployment

### **Smart Change Detection**
- Only deploys GPU container if GPU-related files changed
- Only updates monitoring if monitoring config changed
- Manual override options via workflow dispatch

### **Parallel Execution**
- GPU container and main app deploy in parallel
- Monitoring setup runs after main app deployment
- Faster overall deployment time

### **Comprehensive Health Checks**
- Basic health endpoint validation
- OpenAI API connectivity test
- Vertex AI service verification
- GPU quota availability check

### **Automatic Rollback**
- Detects deployment failures
- Automatically rolls back to previous Cloud Run revision
- Provides detailed failure diagnostics

### **Rich Deployment Summary**
- Visual status indicators for each component
- Direct links to deployed services and monitoring
- Next steps and troubleshooting guidance

## 🎛️ Manual Deployment Options

The unified deployment workflow supports manual triggers with options:

```yaml
workflow_dispatch:
  inputs:
    force_monitoring_update:
      description: 'Force update all monitoring resources'
      type: boolean
    skip_gpu_deployment:
      description: 'Skip GPU container deployment'
      type: boolean
```

## 📁 Backup Files

The following files are kept as backups:
- `main.yml.backup` - Original main deployment workflow
- `deploy-vertex-gpu.yml.backup` - Original GPU deployment workflow
- `setup-monitoring.yml.backup` - Original monitoring setup workflow

## 🔧 Migration Benefits

1. **Reduced Complexity:** 4 workflows → 2 workflows
2. **Atomic Deployments:** All components deploy together
3. **Better Error Handling:** Automatic rollback and cleanup
4. **Improved Visibility:** Single deployment status view
5. **Resource Efficiency:** Shared authentication and setup steps
6. **Smart Optimization:** Skip unnecessary deployments based on changes

## 🚨 Troubleshooting

If deployments fail:

1. **Check the unified workflow logs** in the Actions tab
2. **Review the deployment summary** for specific component failures
3. **Verify GCP permissions** for the service account
4. **Check resource quotas** in Google Cloud Console
5. **Validate secrets** are properly configured

## 🔄 Rollback Process

The workflow includes automatic rollback, but manual rollback can be performed:

```bash
# Get previous revision
gcloud run revisions list --service=av-app --region=us-central1 --limit=2

# Rollback to previous revision
gcloud run services update-traffic av-app --region=us-central1 --to-revisions=REVISION_NAME=100
``` 