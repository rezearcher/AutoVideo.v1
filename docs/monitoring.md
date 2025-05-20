# Monitoring Documentation

## GitHub Actions Monitoring

### 1. Monitor Workflow Script
The `monitor_workflow.sh` script provides real-time monitoring of GitHub Actions workflows.

#### Features
- Shows latest 5 workflow runs
- Color-coded status indicators
- Detailed job information
- Real-time run watching

#### Usage
```bash
./scripts/monitor_workflow.sh
```

#### Output Format
- 🟢 Green: Success/completed
- 🟡 Yellow: In progress/queued
- 🔴 Red: Failed/error

### 2. Manual Monitoring Commands

#### List Workflow Runs
```bash
gh run list
```

#### Watch Specific Run
```bash
gh run watch <run-id>
```

#### View Detailed Logs
```bash
gh run view <run-id> --log
```

## API Testing

### 1. Test API Script
The `test_api.py` script verifies connectivity with all required APIs.

#### Tested Services
- OpenAI API
- ElevenLabs API
- YouTube API

#### Usage
```bash
python test_api.py
```

#### Exit Codes
- 0: All tests passed
- 1: One or more tests failed

## Resource Monitoring

### 1. Cloud Run Metrics
- CPU usage
- Memory usage
- Request latency
- Error rates

### 2. GPU Worker Metrics
- GPU utilization
- Memory usage
- Processing time
- Queue length

## Storage Monitoring

### 1. Cloud Storage Metrics
- Storage usage
- Object count
- Bandwidth usage
- Error rates

### 2. CDN Metrics
- Cache hit rate
- Bandwidth usage
- Error rates
- Latency

## Alerting

### 1. Critical Alerts
- API failures
- Deployment failures
- Resource exhaustion
- Storage quota warnings

### 2. Warning Alerts
- High resource usage
- Slow response times
- Queue buildup
- Storage growth

## Logging

### 1. Application Logs
- Request logs
- Error logs
- Performance metrics
- User actions

### 2. System Logs
- Deployment logs
- Container logs
- API logs
- Security logs

## Performance Monitoring

### 1. Key Metrics
- Response time
- Throughput
- Error rate
- Resource utilization

### 2. Thresholds
- Response time: < 200ms
- Error rate: < 1%
- CPU usage: < 80%
- Memory usage: < 80%

## Maintenance Procedures

### 1. Daily Checks
- Review error logs
- Check resource usage
- Monitor API quotas
- Verify deployments

### 2. Weekly Checks
- Review performance metrics
- Check storage growth
- Analyze error patterns
- Update monitoring rules

### 3. Monthly Checks
- Review resource allocation
- Optimize configurations
- Update monitoring tools
- Plan improvements

## Troubleshooting Guide

### 1. Common Issues

#### API Connectivity
- Check API keys
- Verify network connectivity
- Check rate limits
- Review error messages

#### Deployment Issues
- Check resource quotas
- Verify permissions
- Review build logs
- Check configuration

#### Performance Issues
- Monitor resource usage
- Check queue length
- Review error rates
- Analyze logs

### 2. Resolution Steps

1. Identify the issue
2. Check relevant logs
3. Verify configurations
4. Apply fixes
5. Monitor results

## Future Monitoring Improvements

### 1. Planned Features
- Custom dashboard
- Automated alerts
- Performance analytics
- Cost monitoring

### 2. Integration Plans
- Cloud Monitoring
- Log Analytics
- Performance Insights
- Cost Management 