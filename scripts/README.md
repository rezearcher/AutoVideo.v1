# Scripts Directory

This directory contains utility scripts for the AI Auto Video Generator project.

## Veo Diagnostic Tool

The `veo_diag.py` script is a comprehensive diagnostic tool for checking the Veo SDK integration.

### Usage

```bash
# Basic usage
python scripts/veo_diag.py

# Show verbose output
python scripts/veo_diag.py --verbose

# Output results as JSON
python scripts/veo_diag.py --json
```

### What it checks

1. **Import Functionality**: Verifies all required packages are installed
2. **Authentication**: Validates GCP credentials and project configuration
3. **Dependencies**: Checks versions of required dependencies
4. **API Connection**: Tests connection to the Veo API
5. **Storage Access**: Verifies access to the GCS bucket for video storage

### Troubleshooting

If the diagnostic fails, it will provide recommendations for fixing the issues:

#### Import Errors
- Install the required packages: `pip install google-cloud-aiplatform[preview] google-cloud-storage`
- Make sure you're using Python 3.11 (Python 3.12 has compatibility issues with Veo)

#### Authentication Issues
- Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to point to your service account key
- Verify the service account has the necessary permissions for Vertex AI and Storage

#### API Connection Issues
- Check your quota limits in the Google Cloud Console
- Verify the Veo model is available in your region

#### Storage Access Issues
- Set the `VERTEX_BUCKET_NAME` environment variable
- Ensure the bucket exists and the service account has access to it

### CI/CD Integration

The diagnostic tool is integrated into the deployment workflow and will prevent deployment if it fails, ensuring that the Veo integration is always working properly.

## Other Scripts

- Additional utility scripts will be documented here as they are added. 