"""
Example script demonstrating how to use the YouTube uploader.
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import the youtube_uploader module
sys.path.append(str(Path(__file__).parent.parent))

from youtube_uploader import YouTubeConfig, upload_video


def main():
    # Example video path (replace with your video path)
    video_path = "output/run_20250429_190148/video/final_video.mp4"

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return

    # Example video metadata
    title = "AI Generated Story: The Mysterious Island"
    description = "An AI-generated story about a mysterious island that appears once every hundred years."
    tags = ["AI", "story", "mystery", "island", "generated"]

    # Ask user if they want to upload
    print("Would you like to upload this video to YouTube?")
    print("Press 'y' within 5 seconds to upload, or any other key to skip...")

    # Wait for user input with timeout
    start_time = time.time()
    while time.time() - start_time < 5:
        if sys.stdin.isatty():
            if sys.stdin.read(1).lower() == "y":
                break
        time.sleep(0.1)
    else:
        print("Upload skipped.")
        return

    # Upload the video
    print("Uploading video...")
    video_id = upload_video(video_path, title, description, tags)

    if video_id:
        print(f"Video uploaded successfully! Video ID: {video_id}")
        print(f"Video URL: https://youtube.com/watch?v={video_id}")
    else:
        print("Upload failed. Check the logs for details.")


if __name__ == "__main__":
    main()
