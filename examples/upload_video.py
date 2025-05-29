#!/usr/bin/env python3
"""
Example script to upload a video to YouTube
"""

import os
import sys

# Add the parent directory to the path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_uploader import YouTubeUploader


def main():
    """Upload a test video"""
    uploader = YouTubeUploader()

    # Example video metadata
    video_metadata = {
        "title": "Test Video Upload",
        "description": "This is a test video uploaded via the API",
        "tags": ["test", "api", "upload"],
        "category_id": "22",  # People & Blogs
        "privacy_status": "private",  # private, public, unlisted
    }

    # Path to your video file
    video_path = "path/to/your/video.mp4"

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return

    try:
        video_id = uploader.upload_video(video_path, video_metadata)
        print(f"Video uploaded successfully! Video ID: {video_id}")
    except Exception as e:
        print(f"Upload failed: {e}")


if __name__ == "__main__":
    main()
