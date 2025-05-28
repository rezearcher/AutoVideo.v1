"""
YouTube Uploader Module
Handles video uploads to YouTube, both immediate and scheduled.
"""

import os
import logging
import time
from typing import Optional, List, Dict
from datetime import datetime
from googleapiclient.http import MediaFileUpload
from .token_manager import TokenManager
from .config import YouTubeConfig

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YouTubeUploader:
    """Handles YouTube video uploads and authentication."""

    def __init__(self):
        self.token_manager = TokenManager()
        self.youtube = None

    def authenticate(self):
        """Authenticate with YouTube API using token manager."""
        try:
            self.youtube = self.token_manager.get_youtube_service()
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            return False

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        category_id: str = "22",  # People & Blogs
        privacy_status: str = "public",
    ) -> Optional[str]:
        """
        Upload a video to YouTube.

        Args:
            video_path: Path to the video file
            title: Video title
            description: Video description
            category_id: YouTube category ID
            privacy_status: Video privacy status (private, unlisted, public)

        Returns:
            Video ID if successful, False otherwise
        """
        if not self.youtube:
            if not self.authenticate():
                return False

        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": category_id,
                },
                "status": {"privacyStatus": privacy_status},
            }

            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

            request = self.youtube.videos().insert(
                part=",".join(body.keys()), body=body, media_body=media
            )

            response = request.execute()
            video_id = response["id"]
            video_url = f"https://youtu.be/{video_id}"
            logger.info(f"Video uploaded successfully! Video ID: {video_id}")
            logger.info(f"Watch it here: {video_url}")
            return video_id

        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")
            return False


def upload_video(
    video_path: str,
    title: str,
    description: str,
    category_id: str = "22",  # People & Blogs
    privacy_status: str = "public",
) -> Optional[str]:
    """
    Convenience function to upload a video to YouTube.

    Args:
        video_path: Path to the video file
        title: Video title
        description: Video description
        category_id: YouTube category ID
        privacy_status: Video privacy status (private, unlisted, public)

    Returns:
        Video ID if successful, False otherwise
    """
    uploader = YouTubeUploader()
    return uploader.upload_video(
        video_path, title, description, category_id, privacy_status
    )


def schedule_upload(
    video_path: str,
    schedule_time: datetime,
    title: str,
    description: str,
    category_id: str = "22",  # People & Blogs
    privacy_status: str = "public",
) -> bool:
    """
    Schedule a video for upload at a specific time.

    Args:
        video_path: Path to the video file
        schedule_time: When to upload the video
        title: Video title
        description: Video description
        category_id: YouTube category ID
        privacy_status: Video privacy status (private, unlisted, public)

    Returns:
        True if scheduled successfully, False otherwise
    """
    # TODO: Implement scheduling functionality
    # This could use a task queue like Celery or a simple scheduler
    logger.warning("Scheduling functionality not yet implemented")
    return False
