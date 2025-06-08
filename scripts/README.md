# Diagnostic Scripts

This directory contains diagnostic scripts for troubleshooting and validating various components of the application.

## Veo SDK Diagnostic

The `veo_diag.py` script performs comprehensive checks to diagnose issues with Veo SDK initialization.

### Features

- **Import Verification**: Tests all required imports for Veo SDK (google.auth, vertexai, and preview modules)
- **Authentication Check**: Verifies GCP credentials and project initialization
- **Dependency Analysis**: Ensures proper module separation from MoviePy
- **API Connection Test**: Verifies access to Vertex AI APIs and Veo models (with zero token cost)
- **Storage Access Check**: Tests GCS bucket permissions for read/write operations
- **Actionable Recommendations**: Provides clear recommendations based on test results

### Usage

```bash
# Run locally
python scripts/veo_diag.py

# Environment variables (optional)
export GOOGLE_CLOUD_PROJECT="your-project-id"
export VERTEX_BUCKET_NAME="your-bucket-name"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

### Integration with CI/CD

The script is integrated into our deployment workflow in `.github/workflows/deploy.yml` to automatically run before deployment, ensuring that the Veo SDK will initialize correctly in the deployed environment.

### Exit Codes

- `0`: All tests passed successfully
- `1`: One or more tests failed, check the recommendations for solutions

### Sample Output

```
=== Veo SDK Initialization Test Results ===

IMPORTS TESTS:
  google.auth: success
  vertexai: success
  vertexai_version: 1.46.0
  vertexai.preview.models: success
  vertexai.preview.generative_models: success

AUTH TESTS:
  credentials_file: not found (using default credentials)
  vertexai_init: success
  actual_project: av-8675309
  actual_location: us-central1

DEPENDENCIES TESTS:
  moviepy_compat_importable: true
  veo_moviepy_coupled: false

API TESTS:
  list_models: success
  model_count: 124
  veo_models: ['veo-3.0-generate-preview']
  veo_model_available: true
  model_init: success
  api_ping: initiated

STORAGE TESTS:
  bucket_configured: true
  bucket_exists: true
  write_test: success
  read_test: success
  cleanup: success

=== Recommendations ===
All tests passed! No recommendations needed.
```

### Troubleshooting Guide

If the script reports failures, refer to the recommendations section for specific actions to take. Common issues include:

1. **Python Version Incompatibility**: Use Python 3.11 or lower (Veo SDK doesn't support Python 3.12+)
2. **Missing Dependencies**: Install required packages: `pip install "google-cloud-aiplatform[preview]>=1.96.0"`
3. **Authentication Issues**: Check service account permissions and credentials
4. **Project Mismatch**: Ensure GOOGLE_CLOUD_PROJECT matches the actual project where Veo is enabled
5. **Bucket Access**: Verify the service account has read/write access to the storage bucket 