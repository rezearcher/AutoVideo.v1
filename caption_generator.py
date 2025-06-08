import logging
import os
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.moviepy_compat import CompositeVideoClip, ImageClip, VideoFileClip

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default font paths for different operating systems
DEFAULT_FONT_PATHS = {
    "linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Primary font
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Backup font
        "/app/fonts/DejaVuSans.ttf",  # Local backup
    ],
    "darwin": ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"],
    "win32": ["C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf"],
}


def get_default_font_path():
    """Get the default font path for the current operating system."""
    system = os.name
    if system in DEFAULT_FONT_PATHS:
        # Try each font path in order until one works
        for font_path in DEFAULT_FONT_PATHS[system]:
            if os.path.exists(font_path):
                logger.info(f"Using font: {font_path}")
                return font_path
    # If no fonts found, return the first Linux path as fallback
    logger.warning("No system fonts found, using default fallback")
    return DEFAULT_FONT_PATHS["linux"][0]


def create_caption_images(story, words_per_caption=5, font_path=None):
    """Convert the story into caption segments and generate images."""
    try:
        # Use provided font path or get default
        if not font_path:
            font_path = get_default_font_path()

        # Verify font file exists
        if not os.path.exists(font_path):
            logger.warning(f"Font file not found at {font_path}, trying fallback fonts")
            font_path = get_default_font_path()

        # Split story into words and create segments
        words = story.split()
        caption_segments = [
            " ".join(words[i : i + words_per_caption])
            for i in range(0, len(words), words_per_caption)
        ]

        caption_images = []
        font_size = 40
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            logger.error(f"Error loading font: {str(e)}")
            # Fallback to default font
            logger.warning("Falling back to default font")
            font = ImageFont.load_default()

        # Create caption images
        for segment in caption_segments:
            # Create transparent background
            img = Image.new("RGBA", (1920, 100), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)

            # Add semi-transparent background for text
            text_bbox = d.textbbox((0, 0), segment, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Calculate position for centered text
            x = (1920 - text_width) // 2
            y = (100 - text_height) // 2

            # Draw background rectangle
            d.rectangle(
                [(x - 10, y - 5), (x + text_width + 10, y + text_height + 5)],
                fill=(0, 0, 0, 180),
            )

            # Draw text
            d.text((x, y), segment, fill=(255, 255, 255, 255), font=font)
            caption_images.append(img)

        logger.info(f"Created {len(caption_images)} caption images")
        return caption_images

    except Exception as e:
        logger.error(f"Error creating caption images: {str(e)}")
        raise


def add_captions_to_video(video_path, caption_images, output_path):
    """Overlay captions onto the video."""
    try:
        # Load video
        video_clip = VideoFileClip(video_path)
        total_duration = video_clip.duration
        num_captions = len(caption_images)
        avg_duration_per_caption = total_duration / num_captions

        # Create caption clips
        caption_clips = []
        for idx, caption_img in enumerate(caption_images):
            start_time = idx * avg_duration_per_caption
            end_time = start_time + avg_duration_per_caption
            if end_time > total_duration:
                end_time = total_duration

            caption_img_array = np.array(caption_img)
            caption_clip = (
                ImageClip(caption_img_array)
                .set_duration(end_time - start_time)
                .set_start(start_time)
                .set_position(("center", "bottom"))
            )
            caption_clips.append(caption_clip)

        # Combine video and captions
        final_caption_clip = CompositeVideoClip(caption_clips, size=video_clip.size)
        final_video_clip = CompositeVideoClip(
            [
                video_clip.set_duration(total_duration),
                final_caption_clip.set_duration(total_duration),
            ]
        )

        # Write output video with NVENC hardware encoding
        final_video_clip.write_videofile(
            output_path,
            codec="libx264",
            fps=24,
            audio_codec="aac",
            ffmpeg_params=[
                "-hwaccel",
                "cuda",
                "-c:v",
                "h264_nvenc",
                "-preset",
                "fast",
                "-threads",
                "0",
            ],
        )

        # Clean up
        video_clip.close()
        final_video_clip.close()

        logger.info(f"Captions added successfully to {output_path}")

    except Exception as e:
        logger.error(f"Error adding captions to video: {str(e)}")
        raise
