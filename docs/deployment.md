# Deployment Documentation

## Recent Architecture Updates

### 1. Deployment Pipeline
- Added staging environment for safer deployments
- Separated GPU worker deployment
- Implemented proper resource allocation
- Added comprehensive API testing

### 2. Cloud Infrastructure
- Cloud Run for main application and GPU worker
- Cloud Storage for asset management
- Cloud CDN for content delivery
- Proper IAM roles and permissions

## Deployment Process

### 1. Pre-deployment Checks
```bash
# Run API tests locally
python test_api.py

# Check GitHub Actions status
./scripts/monitor_workflow.sh
```

### 2. Deployment Steps
1. API Tests
   - OpenAI connectivity
   - ElevenLabs connectivity
   - YouTube API credentials
   - Exit code 0 for success, 1 for failure

2. Staging Deployment
   - Deploys to `av-app-staging-939407899550`
   - Resource limits: 2Gi memory, 2 CPU
   - Auto-scaling: 1-5 instances
   - Timeout: 300s

3. Production Deployment
   - Deploys to `av-app-939407899550`
   - Resource limits: 2Gi memory, 2 CPU
   - Auto-scaling: 1-10 instances
   - Timeout: 300s

4. GPU Worker Deployment
   - Deploys to `av-gpu-worker-939407899550`
   - Resource limits: 8Gi memory, 4 CPU, 1 GPU
   - Auto-scaling: 0-5 instances
   - Timeout: 600s

## Monitoring and Debugging

### 1. GitHub Actions Monitoring
```bash
# View latest workflow runs
./scripts/monitor_workflow.sh

# Watch specific run
gh run watch <run-id>

# View detailed logs
gh run view <run-id> --log
```

### 2. Common Issues and Solutions

#### API Test Failures
- Check API keys in GitHub Secrets
- Verify API service status
- Check network connectivity

#### Deployment Failures
- Check resource quotas
- Verify service account permissions
- Check container build logs

#### GPU Worker Issues
- Verify GPU availability
- Check CUDA compatibility
- Monitor GPU memory usage

## Resource Configuration

### 1. Main Application
```yaml
service: av-app
region: us-central1
min_instances: 1
max_instances: 10
memory: 2Gi
cpu: 2
concurrency: 80
timeout: 300s
```

### 2. GPU Worker
```yaml
service: av-gpu-worker
region: us-central1
min_instances: 0
max_instances: 5
memory: 8Gi
cpu: 4
gpu: 1
concurrency: 1
timeout: 600s
```

## Storage Configuration

### 1. Production Storage
```yaml
bucket: av-8675309-video-jobs
location: us-central1
storageClass: STANDARD
versioning: enabled
lifecycle:
  - age: 30
    versions: 3
```

### 2. Staging Storage
```yaml
bucket: av-8675309-staging
location: us-central1
storageClass: STANDARD
versioning: enabled
lifecycle:
  - age: 7
    versions: 2
```

## Security

### 1. Required Secrets
- `OPENAI_API_KEY`
- `ELEVENLABS_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_PROJECT_ID`

### 2. Service Account Permissions
- `roles/storage.admin`
- `roles/run.admin`

## Maintenance

### 1. Regular Checks
- Monitor API usage and quotas
- Check storage lifecycle policies
- Review deployment logs
- Monitor GPU worker performance

### 2. Cleanup Procedures
- Review and clean up old deployments
- Monitor storage usage
- Check for failed jobs
- Review error logs

## Future Improvements

### 1. Planned Updates
- Add more comprehensive testing
- Implement better error handling
- Add performance monitoring
- Improve resource optimization

### 2. Known Limitations
- GPU worker scaling limitations
- Storage cost optimization needed
- API rate limiting considerations
- Deployment time optimization 