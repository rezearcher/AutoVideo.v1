#!/usr/bin/env python3
"""
Standalone GPU Worker for Vertex AI Custom Jobs
Processes video generation tasks with GPU acceleration
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict

from google.cloud import storage
from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    concatenate_videoclips,
)

from caption_generator import add_captions_to_video, create_caption_images

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GPUVideoProcessor:
    def __init__(self, project_id: str, bucket_name: str):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(bucket_name)

    def check_gpu_availability(self) -> bool:
        """Check if NVIDIA GPU is available"""
        try:
            result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("GPU detected successfully")
                logger.info(f"nvidia-smi output:\n{result.stdout}")
                return True
            else:
                logger.error(f"nvidia-smi failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("nvidia-smi not found - no GPU available")
            return False

    def download_job_data(self, job_id: str) -> Dict[str, Any]:
        """Download job configuration from GCS"""
        try:
            blob_name = f"jobs/{job_id}/config.json"
            blob = self.bucket.blob(blob_name)

            if not blob.exists():
                raise FileNotFoundError(f"Job config not found: {blob_name}")

            config_data = json.loads(blob.download_as_text())
            logger.info(f"Downloaded job config for {job_id}")
            return config_data

        except Exception as e:
            logger.error(f"Failed to download job data: {e}")
            raise

    def download_job_assets(
        self, job_data: Dict[str, Any], local_dir: str
    ) -> Dict[str, Any]:
        """Download images and audio from GCS to local directory"""
        try:
            logger.info("Downloading job assets from GCS...")

            # Create local directories
            images_dir = os.path.join(local_dir, "images")
            audio_dir = os.path.join(local_dir, "audio")
            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)

            local_job_data = job_data.copy()

            # Download images
            if "image_urls" in job_data:
                local_image_paths = []
                for i, image_url in enumerate(job_data["image_urls"]):
                    # Extract blob name from GCS URL
                    blob_name = image_url.replace(f"gs://{self.bucket_name}/", "")
                    local_path = os.path.join(images_dir, f"image_{i}.png")

                    blob = self.bucket.blob(blob_name)
                    blob.download_to_filename(local_path)
                    local_image_paths.append(local_path)
                    logger.info(f"Downloaded image {i}: {local_path}")

                local_job_data["image_paths"] = local_image_paths

            # Download audio
            if "audio_url" in job_data:
                blob_name = job_data["audio_url"].replace(
                    f"gs://{self.bucket_name}/", ""
                )
                local_audio_path = os.path.join(audio_dir, "audio.mp3")

                blob = self.bucket.blob(blob_name)
                blob.download_to_filename(local_audio_path)
                local_job_data["audio_path"] = local_audio_path
                logger.info(f"Downloaded audio: {local_audio_path}")

            return local_job_data

        except Exception as e:
            logger.error(f"Failed to download job assets: {e}")
            raise

    def upload_result(
        self, job_id: str, video_path: str, status: str = "completed"
    ) -> str:
        """Upload processed video and status to GCS"""
        try:
            # Upload video file
            video_blob_name = f"jobs/{job_id}/output.mp4"
            video_blob = self.bucket.blob(video_blob_name)

            with open(video_path, "rb") as video_file:
                video_blob.upload_from_file(video_file, content_type="video/mp4")

            video_url = f"gs://{self.bucket_name}/{video_blob_name}"
            logger.info(f"Uploaded video to: {video_url}")

            # Upload status
            status_data = {
                "status": status,
                "video_url": video_url,
                "job_id": job_id,
                "timestamp": str(
                    subprocess.run(
                        ["date", "-Iseconds"], capture_output=True, text=True
                    ).stdout.strip()
                ),
            }

            status_blob_name = f"jobs/{job_id}/status.json"
            status_blob = self.bucket.blob(status_blob_name)
            status_blob.upload_from_string(
                json.dumps(status_data, indent=2), content_type="application/json"
            )

            logger.info(
                f"Uploaded status to: gs://{self.bucket_name}/{status_blob_name}"
            )
            return video_url

        except Exception as e:
            logger.error(f"Failed to upload result: {e}")
            raise

    def create_video_from_assets(
        self, job_data: Dict[str, Any], output_path: str
    ) -> bool:
        """Create video from images and audio with captions using GPU acceleration"""
        try:
            logger.info("Creating video from images and audio with GPU acceleration...")

            image_paths = job_data.get("image_paths", [])
            audio_path = job_data.get("audio_path")
            story = job_data.get("script", "")

            if not image_paths:
                raise ValueError("No image paths provided")
            if not audio_path or not os.path.exists(audio_path):
                raise ValueError(f"Audio file not found: {audio_path}")

            # Create temporary video without captions first
            temp_video_path = output_path.replace(".mp4", "_temp.mp4")

            try:
                # Create clips from images
                logger.info("Creating video clips from images...")
                clips = []

                for image_path in image_paths:
                    if os.path.exists(image_path):
                        clip = ImageClip(image_path).set_duration(
                            5
                        )  # 5 seconds per image
                        clips.append(clip)
                    else:
                        logger.warning(f"Image not found: {image_path}")

                if not clips:
                    raise ValueError("No valid images found")

                # Concatenate all clips
                logger.info("Concatenating video clips...")
                final_clip = concatenate_videoclips(clips)

                # Add audio
                logger.info("Adding audio to video...")
                audio = AudioFileClip(audio_path)
                final_clip = final_clip.set_audio(audio)

                # Write initial video with GPU encoding
                logger.info(f"Writing video with GPU encoding to: {temp_video_path}")
                final_clip.write_videofile(
                    temp_video_path,
                    fps=24,
                    codec="libx264",
                    ffmpeg_params=[
                        "-hwaccel",
                        "cuda",
                        "-c:v",
                        "h264_nvenc",
                        "-preset",
                        "fast",
                    ],
                )

                # Clean up clips
                final_clip.close()
                for clip in clips:
                    clip.close()
                audio.close()

                # Add captions if story is provided
                if story:
                    logger.info("Adding captions to video...")
                    try:
                        # Create caption images
                        caption_images = create_caption_images(story)

                        # Add captions to video
                        add_captions_to_video(
                            temp_video_path, caption_images, output_path
                        )

                        # Remove temporary video
                        if os.path.exists(temp_video_path):
                            os.remove(temp_video_path)

                        logger.info("Captions added successfully")
                    except Exception as caption_error:
                        logger.error(f"Error adding captions: {caption_error}")
                        # Use video without captions
                        shutil.move(temp_video_path, output_path)
                else:
                    # No captions needed, just move the temp video
                    shutil.move(temp_video_path, output_path)

                logger.info("Video creation completed successfully")
                return True

            except Exception as e:
                # Clean up temporary files
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                raise e

        except Exception as e:
            logger.error(f"Error creating video from assets: {e}")
            return False

    def render_video(self, job_data: Dict[str, Any], output_path: str) -> bool:
        """Render video using GPU acceleration"""
        try:
            logger.info("Starting GPU-accelerated video rendering...")

            # Check if we have image and audio assets for full video creation
            if "image_urls" in job_data or "image_paths" in job_data:
                return self.create_video_from_assets(job_data, output_path)

            # Fallback to simple test video for basic jobs
            logger.info("Creating test video with GPU acceleration...")
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=duration=10:size=1920x1080:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=10",
                "-c:v",
                "h264_nvenc",  # Use NVIDIA GPU encoder
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-shortest",
                "-y",  # Overwrite output file
                output_path,
            ]

            logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("Video rendering completed successfully")
                return True
            else:
                logger.error(f"Video rendering failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Video rendering timed out")
            return False
        except Exception as e:
            logger.error(f"Video rendering error: {e}")
            return False

    def process_job(self, job_id: str) -> bool:
        """Main job processing function"""
        try:
            logger.info(f"Processing job: {job_id}")

            # Check GPU availability
            if not self.check_gpu_availability():
                logger.error("No GPU available for processing")
                return False

            # Download job configuration
            job_data = self.download_job_data(job_id)

            # Create temporary working directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download assets if they exist
                if "image_urls" in job_data or "audio_url" in job_data:
                    local_job_data = self.download_job_assets(job_data, temp_dir)
                else:
                    local_job_data = job_data

                # Create temporary output file
                output_path = os.path.join(temp_dir, "output.mp4")

                # Render video
                if self.render_video(local_job_data, output_path):
                    # Upload result
                    self.upload_result(job_id, output_path, "completed")
                    logger.info(f"Job {job_id} completed successfully")
                    return True
                else:
                    # Upload failure status
                    status_data = {
                        "status": "failed",
                        "error": "Video rendering failed",
                        "job_id": job_id,
                    }
                    status_blob = self.bucket.blob(f"jobs/{job_id}/status.json")
                    status_blob.upload_from_string(json.dumps(status_data))
                    return False

        except Exception as e:
            logger.error(f"Job processing failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="GPU Video Processing Worker")
    parser.add_argument("--job-id", required=True, help="Job ID to process")
    parser.add_argument("--project-id", required=True, help="GCP Project ID")
    parser.add_argument("--bucket-name", required=True, help="GCS Bucket name")

    args = parser.parse_args()

    logger.info(f"Starting GPU worker for job: {args.job_id}")

    processor = GPUVideoProcessor(args.project_id, args.bucket_name)
    success = processor.process_job(args.job_id)

    if success:
        logger.info("Job completed successfully")
        sys.exit(0)
    else:
        logger.error("Job failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
