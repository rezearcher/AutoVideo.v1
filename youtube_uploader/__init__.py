"""
YouTube Uploader Module for AI-Auto-Video-Generator
Handles video uploads to YouTube, both immediate and scheduled.
"""

from .uploader import upload_video, schedule_upload
from .config import YouTubeConfig

__all__ = ["upload_video", "schedule_upload", "YouTubeConfig"]
