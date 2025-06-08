import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import vertexai
    from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

    VERTEXAI_AVAILABLE = True
except ImportError:
    logging.warning("Vertexai preview package not available")
    VERTEXAI_AVAILABLE = False

from app.models.generation import VideoGenerationRequest

from app.config import settings
from app.config.storage import get_gcs_uri, get_storage_path
from app.services.prompt_cache import PromptCacheService
from app.services.prompt_enhancer import PromptEnhancerService
from app.services.quota_guard import QuotaGuardService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class VeoService:
    """Service for handling Veo AI video generation."""

    def __init__(self, storage_service: StorageService):
        self._storage_service = storage_service
        self._veo_enabled = settings.VEO_ENABLED
        self._initialized = False
        self._model = None
        self._prompt_enhancer = PromptEnhancerService()
        self._prompt_cache = PromptCacheService(storage_service)
        self._max_tokens_per_minute = int(os.environ.get("VEO_LIMIT_MPM", 60))

        if self._veo_enabled and VERTEXAI_AVAILABLE:
            self._initialize()
        else:
            if not self._veo_enabled:
                logger.info("Veo AI video generation disabled by configuration")
            if not VERTEXAI_AVAILABLE:
                logger.warning(
                    "Veo AI video generation not available: Vertex AI preview package not installed"
                )

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

    def _get_tokens_in_use(self) -> int:
        """
        Get the current number of tokens in use for Veo API.
        Uses the monitoring API for real-time usage data.

        Returns:
            Current token usage (0 if unable to determine)
        """
        try:
            project_id = settings.GCP_PROJECT
            if not project_id:
                logger.warning("No GCP project ID set, cannot check token usage")
                return 0

            # Check if gcloud monitoring is available
            check_cmd = ["gcloud", "help", "monitoring"]
            check_result = subprocess.run(
                check_cmd, capture_output=True, text=True, check=False
            )

            if (
                check_result.returncode != 0
                or "ERROR: (gcloud.monitoring)" in check_result.stderr
            ):
                logger.warning("gcloud monitoring not available in this environment")
                return 0

            # Check if time-series command is available
            cmd = ["gcloud", "monitoring", "time-series", "--help"]
            help_result = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )

            if (
                help_result.returncode != 0
                or "Invalid choice: 'time-series'" in help_result.stderr
            ):
                logger.warning("gcloud monitoring time-series not available")
                return 0

            # Now try to get the token usage
            cmd = [
                "gcloud",
                "monitoring",
                "time-series",
                "list",
                f"--project={project_id}",
                '--filter=metric.type="aiplatform.googleapis.com/generative/tokens_in_use" AND metric.label."base_model"="veo-3.0-generate-001"',
                "--limit=1",
                "--format=value(point.value.int64Value)",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                logger.warning(f"Could not check token usage: {result.stderr}")
                return 0

            # Parse the token usage
            tokens_in_use = 0
            if result.stdout.strip():
                tokens_in_use = int(result.stdout.strip())

            return tokens_in_use

        except Exception as e:
            logger.warning(f"Error checking token usage: {e}")
            return 0

    def _wait_for_token_availability(self, tokens_needed: int) -> bool:
        """
        Wait until enough tokens are available within the per-minute quota.
        Uses minute-based windows to efficiently utilize the quota.

        Args:
            tokens_needed: Number of tokens needed for the operation

        Returns:
            True if tokens became available, False if timed out or failed
        """
        max_wait_minutes = 5  # Maximum number of minutes to wait
        wait_count = 0

        while wait_count < max_wait_minutes:
            current_usage = self._get_tokens_in_use()
            tokens_available = self._max_tokens_per_minute - current_usage

            if tokens_available >= tokens_needed:
                logger.info(
                    f"Sufficient tokens available: {tokens_available}/{self._max_tokens_per_minute}"
                )
                return True

            # Wait until the start of the next minute for quota reset
            current_second = datetime.now(timezone.utc).second
            sleep_time = 60 - current_second + 1

            logger.info(
                f"Veo tokens limited ({current_usage}/{self._max_tokens_per_minute}, "
                f"need {tokens_needed}). Waiting {sleep_time}s for next quota window."
            )

            time.sleep(sleep_time)
            wait_count += 1

        logger.warning(
            f"Timed out waiting for token availability after {max_wait_minutes} minutes"
        )
        return False

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

        # Check quota if everything else is available
        quota_status = {}
        if self.is_available():
            has_quota, quota_details = QuotaGuardService.check_veo_quota()
            if not has_quota:
                status = "limited"
                reason = "Quota limit reached or approaching"
            quota_status = quota_details

        return {
            "status": status,
            "reason": reason,
            "quota": quota_status,
            "tokens_in_use": self._get_tokens_in_use(),
            "tokens_per_minute": self._max_tokens_per_minute,
            "cache_enabled": self._prompt_cache.is_enabled(),
        }

    def generate_video(
        self,
        prompt: str,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        reference_image_path: Optional[str] = None,
        check_quota: bool = True,
        estimated_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> Optional[str]:
        """
        Generate a video using Veo AI based on a prompt.

        Args:
            prompt: Text prompt describing the video
            duration_seconds: Duration of the video in seconds
            aspect_ratio: Aspect ratio of the video ("16:9", "1:1", "9:16")
            reference_image_path: Optional reference image path
            check_quota: Whether to check quota before generation
            estimated_tokens: Estimated tokens needed (calculated if None)
            use_cache: Whether to check and use the prompt cache

        Returns:
            URL of the generated video or None if generation failed
        """
        if not self.is_available():
            logger.warning("Veo AI video generation unavailable")
            return None

        # Enhance the prompt with cinematic details using Gemini
        enhanced_prompt = self._prompt_enhancer.enhance_video_prompt(
            prompt, duration_seconds, aspect_ratio, reference_image_path
        )

        # Pack generation parameters
        gen_params = {
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "has_reference_image": reference_image_path is not None,
        }

        # Check cache first if enabled
        if use_cache and self._prompt_cache.is_enabled():
            cached_url = self._prompt_cache.get_cached_video(
                enhanced_prompt, gen_params
            )
            if cached_url:
                logger.info(f"Using cached video for prompt: '{prompt[:30]}...'")
                return cached_url

        # Estimate token usage based on duration and complexity if not provided
        if estimated_tokens is None:
            estimated_tokens = duration_seconds * 8  # rough estimate

        # Check and wait for quota if requested
        if check_quota:
            # Try the QuotaGuardService first (which checks total limits)
            has_quota, _ = QuotaGuardService.check_veo_quota(
                min_available_tokens=estimated_tokens
            )

            if not has_quota:
                logger.warning(
                    f"Insufficient Veo quota for estimated {estimated_tokens} tokens"
                )

                # Use the precise token-aware wait mechanism for per-minute quotas
                tokens_available = self._wait_for_token_availability(estimated_tokens)

                if not tokens_available:
                    logger.error("Veo quota not available after waiting")
                    return None

        try:
            logger.info(
                f"Generating video with Veo AI. Enhanced prompt: '{enhanced_prompt}'"
            )

            # Use the correct GenerationConfig for Veo API
            gen_config = GenerationConfig(
                temperature=0.4,
                top_p=1.0,
                top_k=32,
                candidate_count=1,
                max_output_tokens=2048,
            )

            # Generate video using the correct method with token-aware retry logic
            max_retries = 3
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    # Generate content
                    response = self._model.generate_content(
                        enhanced_prompt, generation_config=gen_config
                    )
                    break  # Success, exit retry loop
                except Exception as e:
                    error_str = str(e).lower()
                    retry_count += 1

                    # Check for quota/resource errors
                    if (
                        "quota" in error_str
                        or "resource exhausted" in error_str
                        or "limit" in error_str
                    ) and retry_count <= max_retries:

                        # Use token-aware wait for quota reset
                        logger.warning(
                            f"Veo quota limit hit, waiting for next quota window "
                            f"(attempt {retry_count}/{max_retries})"
                        )

                        # Wait until next minute for quota reset
                        if not self._wait_for_token_availability(estimated_tokens):
                            raise Exception("Timed out waiting for token availability")
                    else:
                        # Re-raise other errors or if we've exceeded retries
                        raise

            # Extract video data from response
            if (
                not response
                or not hasattr(response, "candidates")
                or not response.candidates
            ):
                logger.error("Veo AI returned empty response")
                return None

            # Process video from response
            candidate = response.candidates[0]
            if not hasattr(candidate, "content") or not candidate.content:
                logger.error("Veo AI response contains no content")
                return None

            # Extract video part from content
            video_part = None
            for part in candidate.content.parts:
                if hasattr(part, "video") and part.video:
                    video_part = part.video
                    break

            if not video_part:
                logger.error("No video found in Veo AI response")
                return None

            # Save the video to a temporary file
            video_id = f"veo_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp4"
            local_path = f"/tmp/{video_id}"

            # Write video bytes to file
            with open(local_path, "wb") as f:
                f.write(video_part.file_data)

            # Upload to our storage bucket using structured paths
            storage_path = get_storage_path("videos", "veo", video_id)
            public_url = self._storage_service.upload_file(local_path, storage_path)

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

            # Cache the result if caching is enabled
            if use_cache and self._prompt_cache.is_enabled():
                self._prompt_cache.cache_video(
                    enhanced_prompt, gen_params, public_url, storage_path
                )

            logger.info(f"Veo AI video generated successfully: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"Error generating video with Veo AI: {e}")
            return None
