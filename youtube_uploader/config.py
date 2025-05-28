"""
YouTube Configuration Module
Handles YouTube API credentials and settings.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class YouTubeConfig:
    """YouTube API configuration."""

    enabled: bool = False
    channel_id: Optional[str] = None
    default_title: str = "AI Generated Video"
    default_description: str = "This video was generated using AI."
    default_tags: list = None
    default_category: str = "22"  # People & Blogs
    default_privacy: str = "private"  # private, unlisted, public

    def __post_init__(self):
        """Initialize default values."""
        if self.default_tags is None:
            self.default_tags = ["AI", "generated", "video"]

    @classmethod
    def from_env(cls) -> "YouTubeConfig":
        """Load configuration from environment variables."""
        load_dotenv()

        return cls(
            enabled=os.getenv("YOUTUBE_ENABLED", "false").lower() == "true",
            channel_id=os.getenv("YOUTUBE_CHANNEL_ID"),
            default_title=os.getenv("YOUTUBE_DEFAULT_TITLE", cls.default_title),
            default_description=os.getenv(
                "YOUTUBE_DEFAULT_DESCRIPTION", cls.default_description
            ),
            default_tags=(
                os.getenv("YOUTUBE_DEFAULT_TAGS", "").split(",")
                if os.getenv("YOUTUBE_DEFAULT_TAGS")
                else None
            ),
            default_category=os.getenv(
                "YOUTUBE_DEFAULT_CATEGORY", cls.default_category
            ),
            default_privacy=os.getenv("YOUTUBE_DEFAULT_PRIVACY", cls.default_privacy),
        )

    def validate(self) -> bool:
        """Validate the configuration."""
        if not self.enabled:
            return True

        # Check if client secret file exists
        client_secret_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), ".files", "client_secret.json"
        )
        if not os.path.exists(client_secret_path):
            print("Error: client_secret.json not found in .files directory")
            return False

        return True
