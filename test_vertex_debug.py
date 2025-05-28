#!/usr/bin/env python3
"""
Debug script to test Vertex AI initialization step by step
"""

import os
import sys
import time
import logging
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic
from google.cloud import storage
import google.auth

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_vertex_ai_initialization():
    """Test each step of Vertex AI initialization"""

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
    region = "us-central1"
    bucket_name = f"{project_id}-video-jobs"

    logger.info(f"🔧 Testing Vertex AI initialization for project: {project_id}")

    try:
        # Step 1: Test authentication
        logger.info("Step 1: Testing authentication...")
        start_time = time.time()
        credentials, project = google.auth.default()
        logger.info(f"✅ Authentication successful in {time.time() - start_time:.2f}s")
        logger.info(f"   Project: {project}")
        logger.info(f"   Credentials type: {type(credentials).__name__}")

        # Step 2: Test Vertex AI initialization
        logger.info("Step 2: Testing Vertex AI initialization...")
        start_time = time.time()
        aiplatform.init(
            project=project_id, location=region, staging_bucket=f"gs://{bucket_name}"
        )
        logger.info(f"✅ Vertex AI init successful in {time.time() - start_time:.2f}s")

        # Step 3: Test JobServiceClient creation
        logger.info("Step 3: Testing JobServiceClient creation...")
        start_time = time.time()
        job_client = gapic.JobServiceClient(
            client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
        )
        logger.info(f"✅ JobServiceClient created in {time.time() - start_time:.2f}s")

        # Step 4: Test Storage client
        logger.info("Step 4: Testing Storage client...")
        start_time = time.time()
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        logger.info(f"✅ Storage client created in {time.time() - start_time:.2f}s")

        # Step 5: Test bucket access
        logger.info("Step 5: Testing bucket access...")
        start_time = time.time()
        try:
            bucket.reload()
            logger.info(
                f"✅ Bucket access successful in {time.time() - start_time:.2f}s"
            )
            logger.info(f"   Bucket exists: {bucket.exists()}")
        except Exception as e:
            logger.warning(f"⚠️ Bucket access failed: {e}")

        # Step 6: Test API endpoint connectivity
        logger.info("Step 6: Testing API endpoint connectivity...")
        start_time = time.time()
        try:
            # Try to list custom jobs (should work even if empty)
            parent = f"projects/{project_id}/locations/{region}"
            response = job_client.list_custom_jobs(parent=parent, page_size=1)
            logger.info(
                f"✅ API endpoint connectivity successful in {time.time() - start_time:.2f}s"
            )
        except Exception as e:
            logger.error(f"❌ API endpoint connectivity failed: {e}")
            raise

        logger.info("🎉 All Vertex AI initialization steps completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Vertex AI initialization failed: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        import traceback

        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = test_vertex_ai_initialization()
    sys.exit(0 if success else 1)
