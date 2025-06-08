#!/usr/bin/env python3
"""
Veo SDK Diagnostic Tool

This script tests if Veo SDK is correctly installed and configured.
It verifies:
1. Import functionality
2. Authentication
3. GCS bucket access
4. Model existence
5. Zero-token API call functionality

Usage:
    python scripts/veo_diag.py [--verbose]
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("veo-diag")

# Results dictionary
results = {
    "import_checks": {"status": "not_run", "details": {}},
    "auth_checks": {"status": "not_run", "details": {}},
    "dependency_checks": {"status": "not_run", "details": {}},
    "api_checks": {"status": "not_run", "details": {}},
    "storage_checks": {"status": "not_run", "details": {}},
    "overall": {"status": "not_run", "summary": "Diagnostics not yet run"},
}


def check_imports() -> bool:
    """Check if required packages are installed and can be imported."""
    logger.info("Checking imports...")
    results["import_checks"]["status"] = "running"

    # Required imports
    required_imports = [
        "google.cloud.aiplatform",
        "vertexai",
        "vertexai.preview.generative_models",
        "google.cloud.storage",
    ]

    success = True
    for module_name in required_imports:
        try:
            __import__(module_name)
            results["import_checks"]["details"][module_name] = "available"
            logger.info(f"✓ {module_name} available")
        except ImportError as e:
            results["import_checks"]["details"][module_name] = str(e)
            logger.error(f"✗ {module_name} import error: {e}")
            success = False

    results["import_checks"]["status"] = "success" if success else "failure"
    return success


def check_authentication() -> bool:
    """Check if Google Cloud authentication is properly configured."""
    logger.info("Checking authentication...")
    results["auth_checks"]["status"] = "running"

    # Verify credentials are available
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    results["auth_checks"]["details"]["credentials_file"] = creds_file or "Not set"

    if not creds_file:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
    elif not os.path.exists(creds_file):
        logger.error(f"Credentials file {creds_file} does not exist")
        results["auth_checks"]["status"] = "failure"
        return False

    # Try to initialize the storage client to verify credentials
    try:
        from google.cloud import storage

        client = storage.Client()
        project_id = client.project
        results["auth_checks"]["details"]["project_id"] = project_id
        logger.info(f"✓ Authenticated to project: {project_id}")
        results["auth_checks"]["status"] = "success"
        return True
    except Exception as e:
        logger.error(f"✗ Authentication error: {e}")
        results["auth_checks"]["details"]["error"] = str(e)
        results["auth_checks"]["status"] = "failure"
        return False


def check_dependencies() -> bool:
    """Check if the necessary Veo dependencies have the correct versions."""
    logger.info("Checking dependencies...")
    results["dependency_checks"]["status"] = "running"

    dependency_info = {}
    all_ok = True

    try:
        import google.cloud.aiplatform as aip

        dependency_info["google-cloud-aiplatform"] = aip.__version__
        logger.info(f"✓ google-cloud-aiplatform: {aip.__version__}")

        # Check if [preview] is installed
        try:
            import vertexai.preview

            dependency_info["vertexai.preview"] = "available"
            logger.info(f"✓ vertexai.preview: available")
        except ImportError:
            dependency_info["vertexai.preview"] = "missing"
            logger.error(
                "✗ vertexai.preview is missing - make sure to install google-cloud-aiplatform[preview]"
            )
            all_ok = False

        # Check generative models
        try:
            from vertexai.preview.generative_models import GenerativeModel

            dependency_info["generative_models"] = "available"
            logger.info(f"✓ vertexai.preview.generative_models: available")
        except ImportError as e:
            dependency_info["generative_models"] = str(e)
            logger.error(f"✗ generative_models import error: {e}")
            all_ok = False

        # Check Python version
        import sys

        py_version = sys.version_info
        if py_version.major == 3 and py_version.minor > 11:
            dependency_info["python_version"] = (
                f"{py_version.major}.{py_version.minor}.{py_version.micro} (not recommended)"
            )
            logger.warning(
                f"⚠ Python {py_version.major}.{py_version.minor} is not recommended for Veo SDK, use Python 3.11"
            )
        else:
            dependency_info["python_version"] = (
                f"{py_version.major}.{py_version.minor}.{py_version.micro}"
            )
            logger.info(
                f"✓ Python version: {py_version.major}.{py_version.minor}.{py_version.micro}"
            )

    except Exception as e:
        logger.error(f"✗ Dependency check error: {e}")
        dependency_info["error"] = str(e)
        all_ok = False

    results["dependency_checks"]["details"] = dependency_info
    results["dependency_checks"]["status"] = "success" if all_ok else "failure"
    return all_ok


def check_api_connection() -> bool:
    """Check if Veo API is accessible by doing a zero-token probe call."""
    logger.info("Checking API connection...")
    results["api_checks"]["status"] = "running"

    try:
        from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

        # Get the model ID from environment or use default
        model_id = os.environ.get("VEO_MODEL", "veo-3.0-generate-preview")
        results["api_checks"]["details"]["model_id"] = model_id

        # Initialize the model
        logger.info(f"Initializing model {model_id}...")
        model = GenerativeModel(model_id)

        # Prepare a simple prompt
        prompt = "A cinematic landscape shot of mountains at sunset."

        # Make a zero-token request (using returnRawTokens=True to avoid quota usage)
        logger.info(f"Making zero-token API probe with prompt: {prompt}")
        start_time = time.time()

        # Use the method that's actually used in the app
        bucket = os.environ.get("VERTEX_BUCKET_NAME")
        if not bucket:
            logger.warning(
                "VERTEX_BUCKET_NAME not set, skipping generate_video_async test"
            )
            results["api_checks"]["details"][
                "generate_video_async"
            ] = "skipped (no bucket)"
        else:
            # Try to initiate the async call but don't wait for result
            try:
                operation = model.generate_video_async(
                    prompt=prompt,
                    generation_config=GenerationConfig(
                        duration_seconds=5,
                        aspect_ratio="16:9",
                        sample_count=1,  # Required parameter
                        return_raw_tokens=True,  # Zero-token probe
                    ),
                    output_storage=f"gs://{bucket}/veo-diag/",
                )

                # Just check that operation was created, don't wait for completion
                if hasattr(operation, "operation") and operation.operation:
                    logger.info(
                        f"✓ Successfully initiated LRO: {operation.operation.name}"
                    )
                    results["api_checks"]["details"]["generate_video_async"] = {
                        "status": "success",
                        "operation_name": operation.operation.name,
                    }
                else:
                    logger.error("✗ Operation created but no operation ID returned")
                    results["api_checks"]["details"]["generate_video_async"] = {
                        "status": "warning",
                        "error": "No operation ID returned",
                    }
            except Exception as e:
                logger.error(f"✗ generate_video_async error: {e}")
                results["api_checks"]["details"]["generate_video_async"] = {
                    "status": "failure",
                    "error": str(e),
                }

        # Record timing
        elapsed = time.time() - start_time
        results["api_checks"]["details"]["api_latency_sec"] = round(elapsed, 2)
        logger.info(f"API call completed in {elapsed:.2f}s")

        results["api_checks"]["status"] = "success"
        return True

    except Exception as e:
        logger.error(f"✗ API check error: {e}")
        results["api_checks"]["details"]["error"] = str(e)
        results["api_checks"]["status"] = "failure"
        return False


def check_storage_access() -> bool:
    """Check if the GCS bucket for Veo output is accessible."""
    logger.info("Checking storage access...")
    results["storage_checks"]["status"] = "running"

    bucket_name = os.environ.get("VERTEX_BUCKET_NAME")
    if not bucket_name:
        logger.warning("VERTEX_BUCKET_NAME environment variable not set")
        results["storage_checks"]["details"]["bucket_name"] = "Not set"
        results["storage_checks"]["status"] = "warning"
        return False

    results["storage_checks"]["details"]["bucket_name"] = bucket_name

    try:
        from google.cloud import storage

        client = storage.Client()

        # Check if bucket exists
        try:
            bucket = client.get_bucket(bucket_name)
            logger.info(f"✓ Bucket {bucket_name} exists")
            results["storage_checks"]["details"]["bucket_exists"] = True

            # Try writing a test file
            blob = bucket.blob("veo-diag/test.txt")
            blob.upload_from_string("Veo diagnostics test file")
            logger.info(f"✓ Successfully wrote to gs://{bucket_name}/veo-diag/test.txt")
            results["storage_checks"]["details"]["write_access"] = True

            # Try reading the test file
            content = blob.download_as_text()
            if content == "Veo diagnostics test file":
                logger.info(
                    f"✓ Successfully read from gs://{bucket_name}/veo-diag/test.txt"
                )
                results["storage_checks"]["details"]["read_access"] = True
            else:
                logger.error(f"✗ Content mismatch when reading from bucket")
                results["storage_checks"]["details"]["read_access"] = False

            # Clean up
            blob.delete()
            logger.info(f"✓ Successfully deleted gs://{bucket_name}/veo-diag/test.txt")
            results["storage_checks"]["details"]["delete_access"] = True

            results["storage_checks"]["status"] = "success"
            return True

        except Exception as e:
            logger.error(f"✗ Bucket access error: {e}")
            results["storage_checks"]["details"]["error"] = str(e)
            results["storage_checks"]["status"] = "failure"
            return False

    except Exception as e:
        logger.error(f"✗ Storage client error: {e}")
        results["storage_checks"]["details"]["error"] = str(e)
        results["storage_checks"]["status"] = "failure"
        return False


def run_diagnostics() -> Dict[str, Any]:
    """Run all diagnostic checks and return results."""
    logger.info("Starting Veo SDK diagnostics...")

    # Run checks in sequence, stopping if a critical check fails
    imports_ok = check_imports()
    if not imports_ok:
        logger.error("Import checks failed, cannot continue")
        results["overall"]["status"] = "failure"
        results["overall"]["summary"] = "Failed to import required modules"
        return results

    auth_ok = check_authentication()
    if not auth_ok:
        logger.error("Authentication checks failed, cannot continue")
        results["overall"]["status"] = "failure"
        results["overall"]["summary"] = "Failed to authenticate with Google Cloud"
        return results

    deps_ok = check_dependencies()
    storage_ok = check_storage_access()
    api_ok = check_api_connection()

    # Determine overall status
    if imports_ok and auth_ok and deps_ok and storage_ok and api_ok:
        results["overall"]["status"] = "success"
        results["overall"]["summary"] = "All Veo SDK checks passed"
    elif imports_ok and auth_ok and api_ok:
        results["overall"]["status"] = "warning"
        results["overall"][
            "summary"
        ] = "Core Veo SDK functionality works, but some checks failed"
    else:
        results["overall"]["status"] = "failure"
        results["overall"]["summary"] = "Veo SDK is not functioning correctly"

    logger.info(f"Diagnostics complete: {results['overall']['summary']}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veo SDK Diagnostic Tool")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        results = run_diagnostics()

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            # Print a summary to stdout
            print("\n===== Veo SDK Diagnostic Results =====")
            print(
                f"Overall: {results['overall']['status'].upper()} - {results['overall']['summary']}"
            )
            print("\nDetail by category:")
            for category, data in results.items():
                if category != "overall":
                    print(f"- {category}: {data['status'].upper()}")

            if results["overall"]["status"] != "success":
                print("\nRecommended actions:")
                if results["import_checks"]["status"] != "success":
                    print(
                        "- Install required packages: pip install google-cloud-aiplatform[preview] google-cloud-storage"
                    )
                if results["auth_checks"]["status"] != "success":
                    print(
                        "- Check authentication: Set GOOGLE_APPLICATION_CREDENTIALS environment variable"
                    )
                if results["dependency_checks"]["status"] != "success":
                    print(
                        "- Check dependency versions and ensure you're using Python 3.11"
                    )
                if results["storage_checks"]["status"] != "success":
                    print(
                        "- Set VERTEX_BUCKET_NAME environment variable and ensure the bucket exists"
                    )
                if results["api_checks"]["status"] != "success":
                    print("- Check API access and quota limits")

        # Exit with appropriate code
        sys.exit(0 if results["overall"]["status"] == "success" else 1)

    except Exception as e:
        logger.error(f"Diagnostic script error: {e}")
        print(f"Error: {e}")
        sys.exit(2)
