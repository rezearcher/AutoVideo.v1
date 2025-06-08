import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.audio_utils import normalize_final_mix

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video processing and generation."""

    def __init__(self):
        self._local_render_allowed = settings.LOCAL_RENDER_ALLOWED

    def render_video(
        self,
        images: List[str],
        audio_path: Optional[str] = None,
        duration_per_image: float = 5.0,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Render a video from a sequence of images and audio.

        Args:
            images: List of image file paths
            audio_path: Path to audio file for the video
            duration_per_image: Duration to show each image in seconds
            output_path: Path where the output video will be saved

        Returns:
            Path to the rendered video or None if rendering failed
        """
        if not self._local_render_allowed:
            logger.warning("Local video rendering not enabled")
            return None

        if not images:
            logger.error("No images provided for video rendering")
            return None

        try:
            # Create temp directory for intermediate files
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)

                # Create a file with the list of images
                image_list_file = temp_dir_path / "images.txt"
                self._create_image_list_file(
                    images, image_list_file, duration_per_image
                )

                # Set default output path if not provided
                if not output_path:
                    output_path = str(temp_dir_path / "output.mp4")

                # Generate video with FFmpeg
                success = self._generate_video(
                    image_list_file=str(image_list_file),
                    audio_path=audio_path,
                    output_path=output_path,
                )

                if not success:
                    logger.error("Failed to generate video")
                    return None

                logger.info(f"Video rendered successfully: {output_path}")
                return output_path

        except Exception as e:
            logger.exception(f"Error rendering video: {e}")
            return None

    def _create_image_list_file(
        self, images: List[str], output_file: Path, duration_per_image: float
    ) -> None:
        """
        Create a file listing images and their durations for FFmpeg.

        Args:
            images: List of image file paths
            output_file: Path to save the image list
            duration_per_image: Duration for each image in seconds
        """
        with open(output_file, "w") as f:
            for image_path in images:
                f.write(f"file '{image_path}'\n")
                f.write(f"duration {duration_per_image}\n")

            # Add the last image again without duration (required by FFmpeg)
            if images:
                f.write(f"file '{images[-1]}'\n")

    def _generate_video(
        self, image_list_file: str, audio_path: Optional[str], output_path: str
    ) -> bool:
        """
        Generate a video using FFmpeg.

        Args:
            image_list_file: Path to file with image list
            audio_path: Path to audio file
            output_path: Path for output video

        Returns:
            True if video generation was successful, False otherwise
        """
        try:
            # Base FFmpeg command for video
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output files without asking
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                image_list_file,
                "-pix_fmt",
                "yuv420p",  # Standard pixel format for compatibility
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure dimensions are even
            ]

            # If audio is provided, process it
            if audio_path and os.path.exists(audio_path):
                # Create normalized audio in temp location
                temp_audio = f"{output_path}.norm_audio.wav"

                # Normalize the audio for consistent loudness
                if not normalize_final_mix(audio_path, temp_audio):
                    logger.warning("Failed to normalize audio, using original")
                    temp_audio = audio_path

                # Add audio to command
                cmd.extend(["-i", temp_audio, "-c:a", "aac", "-b:a", "192k"])

                # Add shortest flag to match video length with audio
                cmd.append("-shortest")

            # Output file and video codec
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-profile:v",
                    "high",
                    "-crf",
                    "23",  # Balance quality and file size
                    output_path,
                ]
            )

            # Run FFmpeg
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg command failed: {result.stderr}")
                return False

            # Clean up temporary files
            if audio_path and os.path.exists(f"{output_path}.norm_audio.wav"):
                os.remove(f"{output_path}.norm_audio.wav")

            return os.path.exists(output_path)

        except Exception as e:
            logger.exception(f"Error in FFmpeg execution: {e}")
            return False
