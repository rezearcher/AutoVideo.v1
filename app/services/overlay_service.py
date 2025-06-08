"""Service for applying visual overlays to videos."""

import logging
import os
import shlex
import subprocess
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import ffmpeg

from app.config import settings
from app.config.storage import get_gcs_uri, get_storage_path
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class OverlayService:
    """Service for applying visual overlays to videos."""

    # Default positions for overlays
    POSITIONS = {
        "top_left": "10:10",
        "top_right": "W-w-10:10",
        "bottom_left": "10:H-h-10",
        "bottom_right": "W-w-10:H-h-10",
        "top_center": "(W-w)/2:10",
        "bottom_center": "(W-w)/2:H-h-10",
        "center": "(W-w)/2:(H-h)/2",
    }

    # Font presets
    FONT_PRESETS = {
        "title": {
            "font": "DejaVuSans-Bold.ttf",
            "fontsize": 36,
            "fontcolor": "white",
            "box": 1,
            "boxcolor": "black@0.5",
            "boxborderw": 5,
        },
        "subtitle": {
            "font": "DejaVuSans.ttf",
            "fontsize": 28,
            "fontcolor": "white",
            "box": 1,
            "boxcolor": "black@0.4",
            "boxborderw": 3,
        },
        "caption": {
            "font": "DejaVuSans.ttf",
            "fontsize": 24,
            "fontcolor": "white",
            "box": 1,
            "boxcolor": "black@0.4",
            "boxborderw": 3,
        },
    }

    def __init__(self, storage_service: StorageService):
        self._storage_service = storage_service
        self._fonts_dir = settings.FONTS_DIR or "/app/fonts"
        self._ensure_fonts_directory()

    def _ensure_fonts_directory(self):
        """Ensure the fonts directory exists."""
        if not os.path.exists(self._fonts_dir):
            os.makedirs(self._fonts_dir, exist_ok=True)
            logger.info(f"Created fonts directory: {self._fonts_dir}")

    def add_overlay_image(
        self,
        video_path: str,
        image_path: str,
        output_path: str,
        position: str = "bottom_right",
        scale: float = 0.15,  # Scale relative to video width
        opacity: float = 1.0,
        margin_x: int = 20,
        margin_y: int = 20,
    ) -> str:
        """
        Add an image overlay (like a logo) to a video.

        Args:
            video_path: Path to input video
            image_path: Path to overlay image
            output_path: Path for output video
            position: Predefined position key or custom format "x:y"
            scale: Scale factor for the image (relative to video width)
            opacity: Opacity of the overlay (0.0-1.0)
            margin_x: Horizontal margin in pixels
            margin_y: Vertical margin in pixels

        Returns:
            Path to the output video
        """
        try:
            # Get video dimensions
            probe = ffmpeg.probe(video_path)
            video_info = next(s for s in probe["streams"] if s["codec_type"] == "video")
            width = int(video_info["width"])

            # Calculate scale based on video width
            scale_w = int(width * scale)

            # Adjust position string with margins if using preset position
            pos = self.POSITIONS.get(position, position)
            if position in self.POSITIONS:
                # Modify preset positions to include margins
                if "W-w-10" in pos:
                    pos = pos.replace("W-w-10", f"W-w-{margin_x}")
                elif "10:H-h-10" in pos:
                    pos = pos.replace("10:H-h-10", f"{margin_x}:H-h-{margin_y}")
                elif "W-w-10:H-h-10" in pos:
                    pos = pos.replace("W-w-10:H-h-10", f"W-w-{margin_x}:H-h-{margin_y}")
                elif "10:10" in pos:
                    pos = pos.replace("10:10", f"{margin_x}:{margin_y}")

            # Use ffmpeg directly with complex filter
            filter_complex = (
                f"[1:v]scale={scale_w}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo];"
                f"[0:v][logo]overlay={pos}[v]"
            )

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file
                "-i",
                video_path,
                "-i",
                image_path,
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "0:a",
                "-c:a",
                "copy",
                output_path,
            ]

            # Run the command
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            logger.info(f"Added image overlay to video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error adding image overlay: {e}")
            # Fall back to original video
            return video_path

    def add_text_overlay(
        self,
        video_path: str,
        output_path: str,
        text: str,
        position: str = "bottom_center",
        preset: str = "caption",
        custom_font_settings: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> str:
        """
        Add a text overlay to a video.

        Args:
            video_path: Path to input video
            output_path: Path for output video
            text: Text to overlay
            position: Predefined position key or custom format "x:y"
            preset: Font preset name or "custom"
            custom_font_settings: Custom font settings if preset is "custom"
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            Path to the output video
        """
        try:
            # Get font settings
            font_settings = self.FONT_PRESETS.get(preset, self.FONT_PRESETS["caption"])
            if preset == "custom" and custom_font_settings:
                font_settings = custom_font_settings

            # Format font settings for ffmpeg
            font_args = ":".join([f"{k}={v}" for k, v in font_settings.items()])

            # Get position
            pos = self.POSITIONS.get(position, position)

            # Build drawtext filter
            drawtext = f"drawtext=text='{text}':x={pos.split(':')[0]}:y={pos.split(':')[1]}:{font_args}"

            # Add time constraints if specified
            if start_time is not None:
                drawtext += f":enable='between(t,{start_time},{end_time or 9999})'"

            # Use ffmpeg directly
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file
                "-i",
                video_path,
                "-vf",
                drawtext,
                "-c:a",
                "copy",
                output_path,
            ]

            # Run the command
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            logger.info(f"Added text overlay to video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error adding text overlay: {e}")
            # Fall back to original video
            return video_path

    def add_multi_overlays(
        self,
        video_path: str,
        output_path: str,
        overlays: List[Dict[str, Any]],
    ) -> str:
        """
        Add multiple overlays to a video in a single FFmpeg pass.

        Args:
            video_path: Path to input video
            output_path: Path for output video
            overlays: List of overlay specifications:
                      [{"type": "image", "path": "...", "position": "...", ...},
                       {"type": "text", "text": "...", "position": "...", ...}]

        Returns:
            Path to the output video
        """
        try:
            # Prepare inputs and filter complex
            inputs = ["-i", video_path]
            filter_parts = []
            mappings = []

            # Input stream counter (0 is the video)
            input_idx = 0
            last_video = "0:v"

            # Process each overlay
            for i, overlay in enumerate(overlays):
                overlay_type = overlay.get("type", "")

                if overlay_type == "image":
                    # Add image input
                    image_path = overlay.get("path", "")
                    if not image_path:
                        continue

                    inputs.extend(["-i", image_path])
                    input_idx += 1

                    # Get position
                    position = overlay.get("position", "bottom_right")
                    pos = self.POSITIONS.get(position, position)

                    # Get scale
                    scale = overlay.get("scale", 0.15)
                    opacity = overlay.get("opacity", 1.0)

                    # Build filter for this image
                    curr_label = f"v{i}"
                    img_label = f"img{i}"

                    # Scale and adjust opacity
                    filter_parts.append(
                        f"[{input_idx}:v]scale=iw*{scale}:-1,format=rgba,"
                        f"colorchannelmixer=aa={opacity}[{img_label}]"
                    )

                    # Overlay on video
                    filter_parts.append(
                        f"[{last_video}][{img_label}]overlay={pos}[{curr_label}]"
                    )

                    # Update last video stream
                    last_video = curr_label

                elif overlay_type == "text":
                    # Get text parameters
                    text = overlay.get("text", "").replace("'", "\\'")
                    position = overlay.get("position", "bottom_center")
                    pos = self.POSITIONS.get(position, position)
                    preset = overlay.get("preset", "caption")

                    # Get font settings
                    font_settings = dict(
                        self.FONT_PRESETS.get(preset, self.FONT_PRESETS["caption"])
                    )
                    custom_settings = overlay.get("font_settings", {})
                    font_settings.update(custom_settings)

                    # Format font settings
                    font_args = ":".join([f"{k}={v}" for k, v in font_settings.items()])

                    # Build drawtext filter
                    curr_label = f"v{i}"

                    # Time constraints
                    enable_expr = ""
                    if "start_time" in overlay:
                        start_time = overlay["start_time"]
                        end_time = overlay.get("end_time", 9999)
                        enable_expr = f":enable='between(t,{start_time},{end_time})'"

                    # Add drawtext filter
                    filter_parts.append(
                        f"[{last_video}]drawtext=text='{text}':x={pos.split(':')[0]}:"
                        f"y={pos.split(':')[1]}:{font_args}{enable_expr}[{curr_label}]"
                    )

                    # Update last video stream
                    last_video = curr_label

            # Final mapping
            mappings = ["-map", f"[{last_video}]", "-map", "0:a"]

            # Build the full command
            cmd = ["ffmpeg", "-y"]
            cmd.extend(inputs)

            if filter_parts:
                cmd.extend(["-filter_complex", ";".join(filter_parts)])
                cmd.extend(mappings)

            cmd.extend(["-c:a", "copy", output_path])

            # Run the command
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            logger.info(f"Added multiple overlays to video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error adding multiple overlays: {e}")
            # Fall back to original video
            return video_path
