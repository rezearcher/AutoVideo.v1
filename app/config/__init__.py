"""Configuration module for the AI Video Generator."""

import os
from typing import Any, Dict, Optional

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not available


class Settings:
    """Application settings loaded from environment variables."""

    # Google Cloud settings
    GCP_PROJECT: str = os.environ.get("GCP_PROJECT", "av-8675309")
    GCP_PROJECT_NUM: str = os.environ.get("GCP_PROJECT_NUM", "939407899550")
    GCP_PRIMARY_REGION: str = os.environ.get("GCP_PRIMARY_REGION", "us-central1")
    GCP_FALLBACK_REGIONS: list = os.environ.get(
        "GCP_FALLBACK_REGIONS", "us-west1,us-east1,asia-southeast1,europe-west1"
    ).split(",")
    GCS_BUCKET_NAME: str = os.environ.get("GCS_BUCKET_NAME", "")

    # Vertex AI settings
    VERTEX_BUCKET_NAME: str = os.environ.get(
        "VERTEX_BUCKET_NAME", f"{GCP_PROJECT}-video-jobs"
    )
    VERTEX_MACHINE_TYPE: str = os.environ.get("VERTEX_MACHINE_TYPE", "g2-standard-8")

    # Service enablement flags
    VEO_ENABLED: bool = os.environ.get("VEO_ENABLED", "false").lower() == "true"
    TTS_ENABLED: bool = os.environ.get("TTS_ENABLED", "false").lower() == "true"
    PROMPT_CACHE_ENABLED: bool = (
        os.environ.get("PROMPT_CACHE_ENABLED", "true").lower() == "true"
    )

    # Quota and rate limiting
    VEO_LIMIT_MPM: int = int(os.environ.get("VEO_LIMIT_MPM", "60"))  # Tokens per minute
    PROMPT_CACHE_TTL_HOURS: int = int(os.environ.get("PROMPT_CACHE_TTL_HOURS", "24"))

    # Directories
    FONTS_DIR: str = os.environ.get("FONTS_DIR", "/app/fonts")
    TEMP_DIR: str = os.environ.get("TEMP_DIR", "/tmp")

    # Worker settings
    WORKER_TIMEOUT: int = int(os.environ.get("WORKER_TIMEOUT", "600"))  # 10 minutes
    WORKER_CONCURRENCY: int = int(os.environ.get("WORKER_CONCURRENCY", "1"))

    # Audio settings
    AUDIO_NORMALIZATION_LEVEL: float = float(
        os.environ.get("AUDIO_NORMALIZATION_LEVEL", "-16.0")
    )

    # Service URL patterns
    CLOUD_RUN_URL_TEMPLATE: str = "https://av-app-{project_num}.{region}.run.app"

    @property
    def CLOUD_RUN_URL(self) -> str:
        """Get the Cloud Run URL for the current project."""
        return self.CLOUD_RUN_URL_TEMPLATE.format(
            project_num=self.GCP_PROJECT_NUM, region=self.GCP_PRIMARY_REGION
        )

    # Override settings with environment variables
    def __init__(self):
        """Initialize settings from environment variables."""
        for key, value in os.environ.items():
            if hasattr(self, key):
                attr_type = type(getattr(self, key))
                if attr_type == bool:
                    setattr(self, key, value.lower() == "true")
                elif attr_type == int:
                    setattr(self, key, int(value))
                elif attr_type == float:
                    setattr(self, key, float(value))
                else:
                    setattr(self, key, value)


# Create a singleton instance
settings = Settings()
