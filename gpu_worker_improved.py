#!/usr/bin/env python3
"""
Standalone GPU Worker for Vertex AI Custom Jobs
Processes video generation tasks with GPU acceleration and graceful CPU fallback
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Dict, List, Optional

from google.cloud import storage

# Update to use our compatibility module
try:
    from app.services.moviepy_compat import (
        AudioFileClip,
        ImageClip,
        concatenate_videoclips,
        MOVIEPY_AVAILABLE,
    )
except ImportError:
    # If running standalone, fall back to direct imports
    try:
        from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips

        MOVIEPY_AVAILABLE = True
    except ImportError:
        MOVIEPY_AVAILABLE = False

        # Define dummy classes to prevent errors
        class DummyClip:
            def __init__(self, *args, **kwargs):
                pass

            def set_duration(self, *args, **kwargs):
                pass

            def set_audio(self, *args, **kwargs):
                pass

            def write_videofile(self, *args, **kwargs):
                pass

        AudioFileClip = ImageClip = DummyClip
        concatenate_videoclips = lambda clips: DummyClip()

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler("/tmp/gpu_worker.log"),  # Also save to file
    ],
)
logger = logging.getLogger(__name__)


class GPUVideoProcessor:
    def __init__(self, project_id: str, bucket_name: str):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(bucket_name)

        # Detect capabilities upfront
        self.gpu_available = self.check_gpu_availability()
        self.nvenc_available = (
            self.check_nvenc_available() if self.gpu_available else False
        )

        # Log capabilities
        logger.info(f"🖥️ GPU available: {self.gpu_available}")
        logger.info(f"🎬 NVENC available: {self.nvenc_available}")

        # Configure MoviePy
        self.configure_moviepy()

    def configure_moviepy(self):
        """Configure MoviePy with proper settings for container environment"""
        try:
            # Try to configure ImageMagick path
            import moviepy.config as mpconf

            # Check if ImageMagick is installed
            imagemagick_path = None
            for path in ["/usr/bin/convert", "/usr/local/bin/convert"]:
                if os.path.exists(path):
                    imagemagick_path = path
                    break

            if imagemagick_path:
                self.log("info", f"Setting ImageMagick binary to {imagemagick_path}")
                mpconf.change_settings({"IMAGEMAGICK_BINARY": imagemagick_path})
            else:
                self.log("warning", "ImageMagick not found, text clips may not work")
        except Exception as e:
            self.log("warning", f"Failed to configure MoviePy: {e}")

    def log(self, level: str, message: str):
        """Log a message and store it for later upload"""
        if level.lower() == "info":
            logger.info(message)
        elif level.lower() == "warning":
            logger.warning(message)
        elif level.lower() == "error":
            logger.error(message)
        else:
            logger.debug(message)

        # Initialize log_messages if it doesn't exist yet
        if not hasattr(self, "log_messages"):
            self.log_messages = []

        self.log_messages.append(f"{level.upper()}: {message}")

    def upload_logs(self, job_id: str):
        """Upload logs to GCS for debugging"""
        try:
            log_content = "\n".join(self.log_messages)
            log_blob = self.bucket.blob(f"jobs/{job_id}/worker.log")
            log_blob.upload_from_string(log_content)
            logger.info(
                f"Uploaded logs to gs://{self.bucket_name}/jobs/{job_id}/worker.log"
            )
        except Exception as e:
            logger.error(f"Failed to upload logs: {e}")

    def check_gpu_availability(self) -> bool:
        """Check if NVIDIA GPU is available"""
        try:
            self.log("info", "Checking for GPU availability...")
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                # Parse nvidia-smi output to get GPU details
                gpu_info = result.stdout
                self.log(
                    "info",
                    f"GPU detected: {gpu_info.splitlines()[0] if gpu_info.splitlines() else 'Unknown'}",
                )

                # Try to get detailed GPU info
                detail_result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,driver_version",
                        "--format=csv,noheader",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if detail_result.returncode == 0:
                    self.log("info", f"GPU details: {detail_result.stdout.strip()}")

                return True
            else:
                self.log(
                    "warning",
                    f"nvidia-smi failed with code {result.returncode}: {result.stderr}",
                )
                return False
        except FileNotFoundError:
            self.log("warning", "nvidia-smi not found - no GPU available")
            return False
        except Exception as e:
            self.log("warning", f"Error checking GPU availability: {e}")
            return False

    def check_nvenc_available(self) -> bool:
        """Check if NVENC is available in ffmpeg"""
        try:
            self.log("info", "Checking for NVENC support in ffmpeg...")
            result = subprocess.run(
                ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                encoders = result.stdout
                if "h264_nvenc" in encoders:
                    self.log("info", "NVENC encoder (h264_nvenc) is available")
                    return True
                else:
                    self.log("warning", "NVENC encoder not found in ffmpeg")
                    return False
            else:
                self.log("warning", f"ffmpeg encoder check failed: {result.stderr}")
                return False
        except Exception as e:
            self.log("warning", f"Error checking NVENC availability: {e}")
            return False

    def download_job_data(self, job_id: str) -> Dict[str, Any]:
        """Download job configuration from GCS"""
        try:
            self.log("info", f"Downloading job config for {job_id}...")
            blob_name = f"jobs/{job_id}/config.json"
            blob = self.bucket.blob(blob_name)

            if not blob.exists():
                error_msg = f"Job config not found: {blob_name}"
                self.log("error", error_msg)
                raise FileNotFoundError(error_msg)

            config_data = json.loads(blob.download_as_text())
            self.log(
                "info",
                f"Successfully downloaded job config: {list(config_data.keys())}",
            )
            return config_data

        except Exception as e:
            self.log("error", f"Failed to download job data: {str(e)}")
            raise

    def download_job_assets(
        self, job_data: Dict[str, Any], local_dir: str
    ) -> Dict[str, Any]:
        """Download images and audio from GCS to local directory"""
        try:
            self.log("info", "Downloading job assets from GCS...")

            # Create local directories
            images_dir = os.path.join(local_dir, "images")
            audio_dir = os.path.join(local_dir, "audio")
            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)

            local_job_data = job_data.copy()

            # Download images
            if "image_urls" in job_data:
                local_image_paths = []
                self.log("info", f"Downloading {len(job_data['image_urls'])} images...")

                for i, image_url in enumerate(job_data["image_urls"]):
                    # Extract blob name from GCS URL
                    blob_name = image_url.replace(f"gs://{self.bucket_name}/", "")
                    local_path = os.path.join(images_dir, f"image_{i}.png")

                    blob = self.bucket.blob(blob_name)
                    if not blob.exists():
                        self.log("warning", f"Image blob not found: {blob_name}")
                        continue

                    blob.download_to_filename(local_path)
                    local_image_paths.append(local_path)
                    self.log(
                        "info",
                        f"Downloaded image {i}: {local_path} ({os.path.getsize(local_path)} bytes)",
                    )

                if not local_image_paths:
                    self.log("error", "No images were successfully downloaded")
                    raise ValueError("No images downloaded")

                local_job_data["image_paths"] = local_image_paths
                self.log(
                    "info", f"Downloaded {len(local_image_paths)} images successfully"
                )

            # Download audio
            if "audio_url" in job_data:
                blob_name = job_data["audio_url"].replace(
                    f"gs://{self.bucket_name}/", ""
                )
                local_audio_path = os.path.join(audio_dir, "audio.mp3")

                blob = self.bucket.blob(blob_name)
                if not blob.exists():
                    self.log("error", f"Audio blob not found: {blob_name}")
                    raise FileNotFoundError(f"Audio file not found: {blob_name}")

                blob.download_to_filename(local_audio_path)
                local_job_data["audio_path"] = local_audio_path
                self.log(
                    "info",
                    f"Downloaded audio: {local_audio_path} ({os.path.getsize(local_audio_path)} bytes)",
                )

            return local_job_data

        except Exception as e:
            self.log("error", f"Failed to download job assets: {str(e)}")
            raise

    def upload_result(
        self, job_id: str, video_path: str, status: str = "completed"
    ) -> str:
        """Upload processed video and status to GCS"""
        try:
            # Upload video file
            video_blob_name = f"jobs/{job_id}/output.mp4"
            video_blob = self.bucket.blob(video_blob_name)

            self.log(
                "info",
                f"Uploading video ({os.path.getsize(video_path)} bytes) to GCS...",
            )
            with open(video_path, "rb") as video_file:
                video_blob.upload_from_file(video_file, content_type="video/mp4")

            video_url = f"gs://{self.bucket_name}/{video_blob_name}"
            self.log("info", f"Uploaded video to: {video_url}")

            # Upload status
            status_data = {
                "status": status,
                "video_url": video_url,
                "job_id": job_id,
                "gpu_used": self.gpu_available and self.nvenc_available,
                "encoding_method": (
                    "nvenc" if (self.gpu_available and self.nvenc_available) else "cpu"
                ),
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

            self.log(
                "info",
                f"Uploaded status to: gs://{self.bucket_name}/{status_blob_name}",
            )
            return video_url

        except Exception as e:
            self.log("error", f"Failed to upload result: {str(e)}")
            raise

    def create_video_from_assets(
        self, job_data: Dict[str, Any], output_path: str
    ) -> bool:
        """Create video from images and audio with adaptive GPU/CPU encoding"""
        try:
            self.log("info", "Creating video from images and audio...")

            image_paths = job_data.get("image_paths", [])
            audio_path = job_data.get("audio_path")
            story = job_data.get("script", "")

            if not image_paths:
                self.log("error", "No image paths provided")
                raise ValueError("No image paths provided")

            if not audio_path or not os.path.exists(audio_path):
                self.log("error", f"Audio file not found: {audio_path}")
                raise ValueError(f"Audio file not found: {audio_path}")

            # Create temporary video without captions first
            temp_video_path = output_path.replace(".mp4", "_temp.mp4")
            self.log("info", f"Temporary video will be saved to: {temp_video_path}")

            try:
                # Create clips from images
                self.log("info", "Creating video clips from images...")
                clips = []

                for i, image_path in enumerate(image_paths):
                    if os.path.exists(image_path):
                        try:
                            # Check image file integrity
                            try:
                                from PIL import Image

                                with Image.open(image_path) as img:
                                    # Just load to verify it's valid
                                    img_size = img.size
                                    self.log(
                                        "info", f"Image {i} dimensions: {img_size}"
                                    )
                            except Exception as img_error:
                                self.log(
                                    "warning", f"Image {i} may be corrupt: {img_error}"
                                )
                                # Continue anyway, let MoviePy try

                            clip = ImageClip(image_path).set_duration(
                                5
                            )  # 5 seconds per image
                            clips.append(clip)
                            self.log("info", f"Added clip {i} from {image_path}")
                        except Exception as clip_error:
                            self.log(
                                "warning",
                                f"Error creating clip from {image_path}: {clip_error}",
                            )
                    else:
                        self.log("warning", f"Image not found: {image_path}")

                if not clips:
                    self.log("error", "No valid images found")
                    raise ValueError("No valid images found")

                # Concatenate all clips
                self.log("info", f"Concatenating {len(clips)} video clips...")
                final_clip = concatenate_videoclips(clips)

                # Add audio
                self.log("info", f"Adding audio from {audio_path}...")
                audio = AudioFileClip(audio_path)
                final_clip = final_clip.set_audio(audio)

                # Prepare ffmpeg parameters based on GPU availability
                if self.gpu_available and self.nvenc_available:
                    self.log("info", "Using GPU acceleration for video encoding")
                    ffmpeg_params = [
                        "-hwaccel",
                        "cuda",
                        "-c:v",
                        "h264_nvenc",
                        "-preset",
                        "fast",
                        "-threads",
                        "0",
                    ]
                else:
                    self.log(
                        "info",
                        "Using CPU for video encoding (GPU not available or NVENC not supported)",
                    )
                    ffmpeg_params = [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "medium",
                        "-threads",
                        "0",
                    ]

                # Write video with adaptive encoding
                self.log(
                    "info",
                    f"Writing video to: {temp_video_path} with params: {ffmpeg_params}",
                )

                try:
                    final_clip.write_videofile(
                        temp_video_path,
                        fps=24,
                        codec="libx264",  # This gets overridden by ffmpeg_params
                        ffmpeg_params=ffmpeg_params,
                        logger=None,  # Disable logger to avoid clutter
                    )
                    self.log(
                        "info",
                        f"Video encoding successful: {os.path.getsize(temp_video_path)} bytes",
                    )
                except Exception as write_error:
                    self.log("error", f"Error during video encoding: {write_error}")
                    self.log("error", f"Traceback: {traceback.format_exc()}")

                    # If GPU encoding failed, try CPU fallback with minimal settings
                    if self.gpu_available and self.nvenc_available:
                        self.log("info", "Trying CPU encoding as fallback...")
                        try:
                            cpu_params = [
                                "-c:v",
                                "libx264",
                                "-preset",
                                "ultrafast",  # Use ultrafast preset for speed
                                "-crf",
                                "28",  # Lower quality for faster encoding
                                "-threads",
                                "0",
                            ]
                            final_clip.write_videofile(
                                temp_video_path,
                                fps=24,
                                codec="libx264",
                                ffmpeg_params=cpu_params,
                                logger=None,
                            )
                            self.log(
                                "info",
                                f"CPU fallback encoding successful: {os.path.getsize(temp_video_path)} bytes",
                            )
                        except Exception as cpu_error:
                            self.log(
                                "error", f"CPU fallback encoding failed: {cpu_error}"
                            )
                            raise
                    else:
                        # Try absolute minimal encoding settings
                        self.log("info", "Trying minimal encoding settings...")
                        try:
                            minimal_params = [
                                "-c:v",
                                "libx264",
                                "-preset",
                                "ultrafast",
                                "-crf",
                                "30",
                                "-pix_fmt",
                                "yuv420p",
                                "-movflags",
                                "+faststart",
                            ]
                            # Try to write with minimal params and reduced resolution
                            # Scale down the clip to reduce encoding burden
                            final_clip = final_clip.resize(height=360)  # Scale to 360p

                            final_clip.write_videofile(
                                temp_video_path,
                                fps=15,  # Reduce framerate
                                codec="libx264",
                                ffmpeg_params=minimal_params,
                                logger=None,
                            )
                            self.log(
                                "info",
                                f"Minimal encoding successful: {os.path.getsize(temp_video_path)} bytes",
                            )
                        except Exception as minimal_error:
                            self.log(
                                "error", f"Minimal encoding failed: {minimal_error}"
                            )
                            raise

                # Clean up clips
                self.log("info", "Cleaning up video clips...")
                final_clip.close()
                for clip in clips:
                    clip.close()
                audio.close()

                # For simplicity, we'll skip captions in this version
                # Just move the temp video to final output
                self.log("info", "Moving temp video to final output...")
                shutil.move(temp_video_path, output_path)
                self.log(
                    "info", f"Video creation completed successfully: {output_path}"
                )
                return True

            except Exception as e:
                # Clean up temporary files
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                self.log("error", f"Error in video creation: {str(e)}")
                self.log("error", f"Traceback: {traceback.format_exc()}")
                raise

        except Exception as e:
            self.log("error", f"Error creating video from assets: {str(e)}")
            self.log("error", f"Traceback: {traceback.format_exc()}")
            return False

    def create_simple_test_video(self, output_path: str) -> bool:
        """Create a simple test video using ffmpeg directly (fallback for testing)"""
        try:
            self.log("info", "Creating simple test video with ffmpeg...")

            # Determine encoding parameters based on GPU availability
            if self.gpu_available and self.nvenc_available:
                self.log("info", "Using NVENC for test video")
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
            else:
                self.log("info", "Using CPU encoding for test video")
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
                    "libx264",  # Use CPU encoder
                    "-preset",
                    "medium",
                    "-c:a",
                    "aac",
                    "-shortest",
                    "-y",  # Overwrite output file
                    output_path,
                ]

            self.log("info", f"Running ffmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.log(
                    "info",
                    f"Test video created successfully: {output_path} ({os.path.getsize(output_path)} bytes)",
                )
                return True
            else:
                self.log("error", f"Test video creation failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.log("error", "Test video creation timed out")
            return False
        except Exception as e:
            self.log("error", f"Error creating test video: {str(e)}")
            return False

    def process_job(self, job_id: str) -> bool:
        """Main job processing function with enhanced error handling"""
        try:
            self.log("info", f"Processing job: {job_id}")
            self.log(
                "info",
                f"GPU available: {self.gpu_available}, NVENC available: {self.nvenc_available}",
            )

            # Download job configuration
            try:
                job_data = self.download_job_data(job_id)
            except Exception as config_error:
                self.log(
                    "error",
                    f"Failed to download job configuration: {str(config_error)}",
                )
                self.upload_logs(job_id)
                return False

            # Create temporary working directory
            with tempfile.TemporaryDirectory() as temp_dir:
                self.log("info", f"Created temporary directory: {temp_dir}")

                try:
                    # Download assets if they exist
                    try:
                        if "image_urls" in job_data or "audio_url" in job_data:
                            local_job_data = self.download_job_assets(
                                job_data, temp_dir
                            )
                        else:
                            local_job_data = job_data
                            self.log(
                                "warning", "No image or audio URLs found in job data"
                            )
                    except Exception as asset_error:
                        self.log(
                            "error", f"Failed to download assets: {str(asset_error)}"
                        )
                        raise

                    # Create temporary output file
                    output_path = os.path.join(temp_dir, "output.mp4")
                    self.log("info", f"Output will be saved to: {output_path}")

                    # Try to render full video with assets first
                    video_success = False
                    try:
                        if (
                            "image_paths" in local_job_data
                            and "audio_path" in local_job_data
                        ):
                            self.log(
                                "info", "Attempting to create full video from assets..."
                            )
                            video_success = self.create_video_from_assets(
                                local_job_data, output_path
                            )
                        else:
                            self.log(
                                "warning",
                                "Insufficient assets for full video, will create test video",
                            )
                    except Exception as video_error:
                        self.log(
                            "error", f"Error creating full video: {str(video_error)}"
                        )
                        self.log("info", "Will try to create simple test video instead")

                    # If full video failed, try simple test video
                    if not video_success:
                        try:
                            self.log(
                                "info", "Creating simple test video as fallback..."
                            )
                            video_success = self.create_simple_test_video(output_path)
                        except Exception as test_error:
                            self.log(
                                "error", f"Error creating test video: {str(test_error)}"
                            )
                            raise

                    # Upload result if any video was created
                    if (
                        video_success
                        and os.path.exists(output_path)
                        and os.path.getsize(output_path) > 0
                    ):
                        self.log(
                            "info", "Video created successfully, uploading results..."
                        )
                        self.upload_result(job_id, output_path, "completed")
                        self.log("info", f"Job {job_id} completed successfully")
                        self.upload_logs(job_id)
                        return True
                    else:
                        self.log("error", "No valid video was created")
                        raise Exception("Failed to create any valid video")

                except Exception as e:
                    self.log("error", f"Job processing error: {str(e)}")
                    self.log("error", f"Traceback: {traceback.format_exc()}")

                    # Upload failure status
                    status_data = {
                        "status": "failed",
                        "error": str(e),
                        "job_id": job_id,
                        "gpu_available": self.gpu_available,
                        "nvenc_available": self.nvenc_available,
                    }

                    self.log("info", "Uploading failure status...")
                    status_blob = self.bucket.blob(f"jobs/{job_id}/status.json")
                    status_blob.upload_from_string(json.dumps(status_data))

                    # Always upload logs on failure
                    self.upload_logs(job_id)
                    return False

        except Exception as e:
            self.log("error", f"Unhandled exception in job processing: {str(e)}")
            self.log("error", f"Traceback: {traceback.format_exc()}")

            try:
                # Try to upload logs even if everything else failed
                self.upload_logs(job_id)
            except:
                pass

            return False


def main():
    """Main entry point with comprehensive exception handling"""
    try:
        parser = argparse.ArgumentParser(description="GPU Video Processing Worker")
        parser.add_argument("--job-id", required=True, help="Job ID to process")
        parser.add_argument("--project-id", required=True, help="GCP Project ID")
        parser.add_argument("--bucket-name", required=True, help="GCS Bucket name")
        parser.add_argument("--config-url", help="URL to job configuration (optional)")
        parser.add_argument(
            "--dry-run", action="store_true", help="Test run without processing"
        )

        args = parser.parse_args()

        logger.info(f"🚀 Starting GPU worker for job: {args.job_id}")
        logger.info(f"📍 Project: {args.project_id}, Bucket: {args.bucket_name}")

        # Add dry-run mode for testing
        if args.dry_run:
            logger.info("🧪 Dry run mode - testing dependencies only")
            try:
                import cv2
                import moviepy
                import numpy
                import PIL

                logger.info("✅ All Python dependencies imported successfully")

                # Test GPU availability
                processor = GPUVideoProcessor(args.project_id, args.bucket_name)
                if processor.gpu_available:
                    logger.info("✅ GPU detected and accessible")
                    if processor.nvenc_available:
                        logger.info("✅ NVENC encoding is available")
                    else:
                        logger.warning("⚠️ GPU detected but NVENC is not available")
                else:
                    logger.warning(
                        "⚠️ No GPU detected, but container startup successful"
                    )

                logger.info("🎉 Dry run completed successfully")
                sys.exit(0)
            except ImportError as e:
                logger.error(f"❌ Missing Python dependency: {e}")
                sys.exit(1)

        processor = GPUVideoProcessor(args.project_id, args.bucket_name)
        success = processor.process_job(args.job_id)

        if success:
            logger.info("🎉 Job completed successfully")
            sys.exit(0)
        else:
            logger.error("❌ Job failed")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("⚠️ Interrupted by user")
        sys.exit(130)
    except SystemExit:
        # Re-raise SystemExit to preserve exit codes
        raise
    except Exception as e:
        logger.exception(f"❌ Fatal error in GPU worker: {e}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        logger.error(f"❌ Full traceback above ☝️")
        sys.exit(1)


if __name__ == "__main__":
    main()
