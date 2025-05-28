"""
YouTube Uploader Module for AI-Auto-Video-Generator
Handles video uploads to YouTube, both immediate and scheduled.
"""

from .config import YouTubeConfig
from .uploader import schedule_upload, upload_video

__all__ = ["upload_video", "schedule_upload", "YouTubeConfig"]
