import os
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple

try:
    import vertexai
    from vertexai.preview.generative_models import GenerativeModel
    VERTEXAI_AVAILABLE = True
except ImportError:
    logging.warning("Vertexai preview package not available")
    VERTEXAI_AVAILABLE = False

from app.config import settings
from app.models.generation import VideoGenerationRequest
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

class VeoService:
    """Service for handling Veo AI video generation."""
    
    def __init__(self, storage_service: StorageService):
        self._storage_service = storage_service
        self._veo_enabled = settings.VEO_ENABLED
        self._initialized = False
        self._model = None
        
        if self._veo_enabled and VERTEXAI_AVAILABLE:
            self._initialize()
        else:
            if not self._veo_enabled:
                logger.info("Veo AI video generation disabled by configuration")
            if not VERTEXAI_AVAILABLE:
                logger.warning("Veo AI video generation not available: Vertex AI preview package not installed")
                
    def _initialize(self):
        """Initialize the Veo model."""
        try:
            vertexai.init(project=settings.GCP_PROJECT, location="us-central1")
            self._model = GenerativeModel("veo-3.0-generate-preview")
            self._initialized = True
            logger.info("Veo AI model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Veo AI model: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if Veo video generation is available."""
        return self._veo_enabled and self._initialized and VERTEXAI_AVAILABLE
        
    def health_check(self) -> Dict[str, Any]:
        """Get health status of the Veo service."""
        status = "available" if self.is_available() else "unavailable"
        reason = None
        
        if not self._veo_enabled:
            reason = "Veo disabled by configuration"
        elif not VERTEXAI_AVAILABLE:
            reason = "Vertex AI preview package not installed"
        elif not self._initialized:
            reason = "Veo AI model initialization failed"
            
        return {
            "status": status,
            "reason": reason
        }
        
    def generate_video(self, 
                       prompt: str, 
                       duration_seconds: int = 5,
                       aspect_ratio: str = "16:9") -> Optional[str]:
        """
        Generate a video using Veo AI based on a prompt.
        
        Args:
            prompt: Text prompt describing the video
            duration_seconds: Duration of the video in seconds
            aspect_ratio: Aspect ratio of the video ("16:9", "1:1", "9:16")
            
        Returns:
            URL of the generated video or None if generation failed
        """
        if not self.is_available():
            logger.warning("Veo AI video generation unavailable")
            return None
            
        try:
            logger.info(f"Generating video with Veo AI. Prompt: '{prompt}'")
            
            generation_config = {
                "durationSeconds": duration_seconds,
                "aspectRatio": aspect_ratio,
                "sampleCount": 1
            }
            
            # Start async generation
            op = self._model.generate_video_async(
                prompt,
                generation_config=generation_config
            )
            
            # Wait for completion (with timeout)
            logger.info("Waiting for Veo video generation to complete...")
            response = op.result(timeout=600)  # 10 minute timeout
            
            if not response or not response.videos or len(response.videos) == 0:
                logger.error("Veo AI returned empty response")
                return None
                
            # Get the GCS URI of the generated video
            video_uri = response.videos[0].gcs_uri
            logger.info(f"Veo AI video generated successfully: {video_uri}")
            
            # Download from GCS and upload to our bucket
            local_path = f"/tmp/veo_{uuid.uuid4()}.mp4"
            self._storage_service.download_from_gcs(video_uri, local_path)
            
            # Upload to our bucket
            video_id = f"veo_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp4"
            storage_path = f"videos/veo/{video_id}"
            public_url = self._storage_service.upload_file(local_path, storage_path)
            
            # Clean up
            if os.path.exists(local_path):
                os.remove(local_path)
                
            return public_url
            
        except Exception as e:
            logger.error(f"Error generating video with Veo AI: {e}")
            return None 