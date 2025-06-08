"""Service for caching Veo API responses based on prompts."""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple, Union

from app.config import settings
from app.config.storage import get_gcs_uri, get_storage_path
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class PromptCacheService:
    """
    Service for caching Veo API responses to save quota.
    Uses a combination of in-memory cache and GCS for persistence.
    """

    def __init__(self, storage_service: StorageService):
        self._storage_service = storage_service
        self._cache = {}  # In-memory cache
        self._cache_ttl = int(os.environ.get("PROMPT_CACHE_TTL_HOURS", 24)) * 3600
        self._cache_enabled = settings.PROMPT_CACHE_ENABLED

    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._cache_enabled

    def _compute_key(self, prompt: str, params: Dict[str, Any]) -> str:
        """
        Compute a stable cache key for a prompt and parameters.

        Args:
            prompt: The text prompt
            params: Generation parameters (duration, aspect_ratio, etc.)

        Returns:
            SHA-256 hash as hexadecimal string
        """
        # Ensure stable serialization by sorting dict keys
        params_str = json.dumps(params, sort_keys=True)
        combined = f"{prompt}|{params_str}"

        # Compute SHA-256 hash
        key = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return key

    def get_cached_video(self, prompt: str, params: Dict[str, Any]) -> Optional[str]:
        """
        Check if a video for this prompt and parameters is cached.

        Args:
            prompt: The text prompt
            params: Generation parameters (duration, aspect_ratio, etc.)

        Returns:
            Public URL of cached video if found, None otherwise
        """
        if not self.is_enabled():
            return None

        # Compute cache key
        cache_key = self._compute_key(prompt, params)

        # Check in-memory cache first
        cached_entry = self._cache.get(cache_key)
        if cached_entry:
            # Verify the entry is not expired
            if cached_entry.get("expires_at", 0) > time.time():
                logger.info(f"In-memory cache hit for prompt: {prompt[:30]}...")
                return cached_entry.get("video_url")
            else:
                # Remove expired entry
                self._cache.pop(cache_key, None)

        # Check GCS cache
        cache_metadata_path = get_storage_path("videos", "cache", f"{cache_key}.json")
        if self._storage_service.file_exists(cache_metadata_path):
            try:
                # Download and parse metadata
                local_path = f"/tmp/cache_{cache_key}.json"
                self._storage_service.download_file(cache_metadata_path, local_path)

                with open(local_path, "r") as f:
                    metadata = json.load(f)

                # Clean up
                if os.path.exists(local_path):
                    os.remove(local_path)

                # Check if entry is expired
                if metadata.get("expires_at", 0) > time.time():
                    # Update in-memory cache
                    self._cache[cache_key] = metadata
                    logger.info(f"GCS cache hit for prompt: {prompt[:30]}...")
                    return metadata.get("video_url")
                else:
                    # Clean up expired entry
                    self._storage_service.delete_file(cache_metadata_path)
                    video_path = metadata.get("video_path")
                    if video_path:
                        self._storage_service.delete_file(video_path)
            except Exception as e:
                logger.warning(f"Error reading cache metadata: {e}")

        return None

    def cache_video(
        self, prompt: str, params: Dict[str, Any], video_url: str, video_path: str
    ) -> bool:
        """
        Cache a video for this prompt and parameters.

        Args:
            prompt: The text prompt
            params: Generation parameters (duration, aspect_ratio, etc.)
            video_url: Public URL of the video
            video_path: Storage path of the video

        Returns:
            True if caching was successful, False otherwise
        """
        if not self.is_enabled():
            return False

        try:
            # Compute cache key
            cache_key = self._compute_key(prompt, params)

            # Create metadata
            expires_at = time.time() + self._cache_ttl
            metadata = {
                "prompt": prompt,
                "params": params,
                "video_url": video_url,
                "video_path": video_path,
                "created_at": time.time(),
                "expires_at": expires_at,
                "cache_key": cache_key,
            }

            # Update in-memory cache
            self._cache[cache_key] = metadata

            # Write to GCS
            local_metadata_path = f"/tmp/cache_{cache_key}.json"
            with open(local_metadata_path, "w") as f:
                json.dump(metadata, f)

            metadata_path = get_storage_path("videos", "cache", f"{cache_key}.json")
            self._storage_service.upload_file(local_metadata_path, metadata_path)

            # Clean up
            if os.path.exists(local_metadata_path):
                os.remove(local_metadata_path)

            logger.info(f"Cached video for prompt: {prompt[:30]}...")
            return True

        except Exception as e:
            logger.error(f"Error caching video: {e}")
            return False

    def clear_expired_cache(self) -> int:
        """
        Clear expired cache entries from memory and GCS.

        Returns:
            Number of entries cleared
        """
        if not self.is_enabled():
            return 0

        count = 0
        now = time.time()

        # Clear expired entries from in-memory cache
        expired_keys = [
            k for k, v in self._cache.items() if v.get("expires_at", 0) < now
        ]
        for key in expired_keys:
            self._cache.pop(key, None)
            count += 1

        # GCS cleanup should be done via lifecycle rules
        # but we could implement a manual cleanup here if needed

        logger.info(f"Cleared {count} expired cache entries")
        return count
