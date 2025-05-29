#!/usr/bin/env python3
"""
Minimal test script to isolate Vertex AI client initialization issues.
This helps identify if the hang occurs during import, aiplatform.init(), or client creation.
"""

import logging
import os
import sys
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_vertex_ai_init():
    """Test Vertex AI initialization step by step"""

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
    region = "us-central1"

    logger.info("🧪 Starting Vertex AI initialization test...")
    logger.info(f"📋 Project: {project_id}, Region: {region}")

    try:
        # Step 1: Test imports
        logger.info("1️⃣ Testing imports...")
        start_time = time.time()

        import google.auth
        from google.cloud import aiplatform
        from google.cloud.aiplatform import gapic

        import_time = time.time() - start_time
        logger.info(f"✅ Imports successful in {import_time:.2f}s")

        # Step 2: Test aiplatform.init()
        logger.info("2️⃣ Testing aiplatform.init()...")
        start_time = time.time()

        aiplatform.init(project=project_id, location=region)

        init_time = time.time() - start_time
        logger.info(f"✅ aiplatform.init() successful in {init_time:.2f}s")

        # Step 3: Test GAPIC client creation
        logger.info("3️⃣ Testing JobServiceClient creation...")
        start_time = time.time()

        client = gapic.JobServiceClient(
            client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
        )

        client_time = time.time() - start_time
        logger.info(f"✅ JobServiceClient created in {client_time:.2f}s")
        logger.info(f"🎯 Client info: {type(client).__name__}")

        # Step 4: Test basic client operation (list jobs)
        logger.info("4️⃣ Testing basic client operation...")
        start_time = time.time()

        parent = f"projects/{project_id}/locations/{region}"
        try:
            # This should either work or fail fast with a clear error
            response = client.list_custom_jobs(parent=parent, timeout=30)
            operation_time = time.time() - start_time
            logger.info(f"✅ Client operation successful in {operation_time:.2f}s")

            # Count jobs (just for info)
            job_count = len(list(response))
            logger.info(f"📊 Found {job_count} existing jobs")

        except Exception as op_error:
            operation_time = time.time() - start_time
            logger.warning(
                f"⚠️ Client operation failed in {operation_time:.2f}s: {op_error}"
            )
            logger.warning(
                "This might be normal if no jobs exist or permissions are limited"
            )

        logger.info("🎉 All Vertex AI initialization tests completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Vertex AI initialization test failed: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        import traceback

        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def test_network_connectivity():
    """Test basic network connectivity to Vertex AI endpoints"""

    logger.info("🌐 Testing network connectivity...")

    import subprocess

    endpoints = [
        f"us-central1-aiplatform.googleapis.com",
        "aiplatform.googleapis.com",
        "googleapis.com",
    ]

    for endpoint in endpoints:
        try:
            logger.info(f"🔍 Testing connectivity to {endpoint}...")

            # Test DNS resolution
            result = subprocess.run(
                ["nslookup", endpoint], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                logger.info(f"✅ DNS resolution successful for {endpoint}")
            else:
                logger.warning(
                    f"⚠️ DNS resolution failed for {endpoint}: {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            logger.error(f"🕐 DNS lookup timed out for {endpoint}")
        except FileNotFoundError:
            logger.warning("⚠️ nslookup not available, skipping DNS test")
            break
        except Exception as e:
            logger.error(f"❌ Network test failed for {endpoint}: {e}")


if __name__ == "__main__":
    logger.info("🚀 Starting Vertex AI diagnostic tests...")

    # Test network first
    test_network_connectivity()

    # Test Vertex AI initialization
    success = test_vertex_ai_init()

    if success:
        logger.info(
            "🎯 All tests passed! Vertex AI should work in the main application."
        )
        sys.exit(0)
    else:
        logger.error(
            "💥 Tests failed! This explains why the main application hangs."
        )
        sys.exit(1)
