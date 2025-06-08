"""Storage configuration and path management."""

import os
from typing import Dict, Optional

from app.config import settings

# Base bucket name from settings
BUCKET_NAME = settings.GCS_BUCKET_NAME

# Structured bucket paths
BUCKET_PATHS = {
    "audio": {
        "tts": "audio/tts",  # Voice-over files
        "music": "audio/music",  # Background music stems
        "final": "audio/final",  # Mixed and normalized audio
    },
    "images": {
        "raw": "images/raw",  # Original input images
        "generated": "images/generated",  # AI-generated images
        "assets": "images/assets",  # Logos, watermarks, overlays
    },
    "videos": {
        "clips": "videos/clips",  # Individual scene clips
        "veo": "videos/veo",  # Raw Veo generations
        "final": "videos/final",  # Final concatenated videos
        "cache": "videos/cache",  # Prompt cache for Veo API
    },
    "fonts": "fonts",  # Font assets
    "temp": "temp",  # Temporary working files (24h lifecycle)
}


def get_storage_path(
    category: str, subcategory: Optional[str] = None, filename: str = ""
) -> str:
    """
    Generate a GCS storage path based on category and subcategory.

    Args:
        category: Main category (audio, images, videos)
        subcategory: Optional subcategory
        filename: Optional filename to append

    Returns:
        Full GCS path without bucket prefix
    """
    if (
        subcategory
        and category in BUCKET_PATHS
        and isinstance(BUCKET_PATHS[category], dict)
    ):
        base_path = BUCKET_PATHS[category].get(subcategory, "")
    else:
        base_path = BUCKET_PATHS.get(category, "")

    if not base_path:
        raise ValueError(f"Invalid storage path category: {category}/{subcategory}")

    return os.path.join(base_path, filename) if filename else base_path


def get_gcs_uri(path: str) -> str:
    """
    Convert a storage path to a full GCS URI.

    Args:
        path: Storage path (without bucket prefix)

    Returns:
        Full GCS URI (gs://bucket/path)
    """
    return f"gs://{BUCKET_NAME}/{path}"
