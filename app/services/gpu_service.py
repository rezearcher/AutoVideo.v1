"""
GPU Service Module
Handles initialization and access to the VertexGPUJobService
"""

import logging
import os
import traceback

logger = logging.getLogger(__name__)

# Global service instance
gpu_service_instance = None


def bootstrap():
    """Initialize the GPU service for the application"""
    global gpu_service_instance

    try:
        import google.auth

        from vertex_gpu_service import VertexGPUJobService

        # Get the current project ID
        credentials, project_id = google.auth.default()
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "av-8675309")

        # Initialize global Vertex AI GPU service
        logger.info("🚀 Bootstrapping VertexGPUJobService...")

        bucket_name = os.getenv("VERTEX_BUCKET_NAME", f"{project_id}-video-jobs")
        logger.info(f"Using bucket name: {bucket_name} for Vertex GPU service")

        gpu_service_instance = VertexGPUJobService(
            project_id=project_id, region="us-central1", bucket_name=bucket_name
        )

        logger.info("✅ VertexGPUJobService bootstrapped successfully")
        return gpu_service_instance

    except Exception as e:
        logger.error(f"⚠️ Failed to bootstrap VertexGPUJobService: {str(e)}")
        logger.error(f"⚠️ Error details: {traceback.format_exc()}")
        logger.warning(
            "Video generation via GPU will be unavailable, but app will continue"
        )
        return None


def get_instance():
    """Get the VertexGPUJobService instance or initialize it if needed"""
    global gpu_service_instance

    if gpu_service_instance is None:
        return bootstrap()

    return gpu_service_instance
