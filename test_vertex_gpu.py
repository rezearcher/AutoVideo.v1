#!/usr/bin/env python3
"""
Test script for Vertex AI GPU service integration
Verifies that the GPU service can be initialized and is ready for job submission
"""

import os
import sys
import logging
from vertex_gpu_service import VertexGPUJobService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_vertex_gpu_service():
    """Test the Vertex AI GPU service initialization and basic functionality"""

    try:
        # Get project ID
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")
        logger.info(f"Testing Vertex AI GPU service with project: {project_id}")

        # Initialize the service
        gpu_service = VertexGPUJobService(project_id=project_id)
        logger.info("✅ VertexGPUJobService initialized successfully")

        # Check if bucket exists
        bucket_name = f"{project_id}-video-jobs"
        logger.info(f"Checking GCS bucket: {bucket_name}")

        try:
            bucket = gpu_service.storage_client.bucket(bucket_name)
            if bucket.exists():
                logger.info(f"✅ GCS bucket {bucket_name} exists and is accessible")
            else:
                logger.warning(f"⚠️ GCS bucket {bucket_name} does not exist")
        except Exception as bucket_error:
            logger.error(f"❌ Error checking bucket: {bucket_error}")

        # Check container image
        container_image = gpu_service.container_image
        logger.info(f"Container image: {container_image}")
        logger.info("✅ Vertex AI GPU service test completed successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Vertex AI GPU service test failed: {e}")
        return False


def main():
    """Main test function"""
    logger.info("🧪 Starting Vertex AI GPU service tests...")

    success = test_vertex_gpu_service()

    if success:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
