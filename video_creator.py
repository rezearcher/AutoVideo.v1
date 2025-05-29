import logging
import os
import textwrap
from datetime import datetime

from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.fx.all import resize
from PIL import Image, ImageDraw, ImageFont

from caption_generator import add_captions_to_video, create_caption_images

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_video(images, voiceover_path, story, timestamp, output_path):
    """
    Create a video from images and audio using MoviePy.

    Args:
        images (list): List of paths to images
        voiceover_path (str): Path to audio file
        story (str): The story text for captions
        timestamp (str): Timestamp for unique file naming
        output_path (str): Path to save the video

    Returns:
        str: Path to the generated video
    """
    try:
        # Validate input files
        logging.info("Validating input files...")
        for image_path in images:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            if not os.path.getsize(image_path) > 0:
                raise ValueError(f"Image file is empty: {image_path}")
            logging.info(f"Validated image: {image_path}")

        # Validate voiceover file
        if not os.path.exists(voiceover_path):
            raise FileNotFoundError(f"Voiceover file not found: {voiceover_path}")
        if not os.path.getsize(voiceover_path) > 0:
            raise ValueError(f"Voiceover file is empty: {voiceover_path}")
        logging.info(f"Validated voiceover: {voiceover_path}")

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create clips from images
        logging.info("Creating video clips from images...")
        clips = []

        for image_path in images:
            try:
                clip = ImageClip(image_path)
                clip = clip.set_duration(5)  # Set duration for each image
                clips.append(clip)
                logging.info(f"Created clip for image: {image_path}")
            except Exception as e:
                raise Exception(
                    f"Error creating clip for image {image_path}: {str(e)}"
                )

        # Concatenate all clips
        logging.info("Concatenating video clips...")
        try:
            final_clip = concatenate_videoclips(clips)
        except Exception as e:
            raise Exception(f"Error concatenating clips: {str(e)}")

        # Add audio
        logging.info("Adding audio to video...")
        try:
            # Verify voiceover file exists and has content before loading
            if not os.path.exists(voiceover_path):
                raise FileNotFoundError(
                    f"Voiceover file not found at path: {voiceover_path}"
                )
            if os.path.getsize(voiceover_path) == 0:
                raise ValueError(f"Voiceover file is empty: {voiceover_path}")

            audio = AudioFileClip(voiceover_path)
            final_clip = final_clip.set_audio(audio)
            logging.info(f"Successfully added audio from: {voiceover_path}")
        except Exception as e:
            raise Exception(f"Error adding audio from {voiceover_path}: {str(e)}")

        # Write the initial video file
        logging.info(f"Writing initial video to: {output_path}")
        try:
            final_clip.write_videofile(
                output_path, fps=24, codec="libx264", audio_codec="aac"
            )
        except Exception as e:
            raise Exception(f"Error writing video file: {str(e)}")

        # Generate and add captions
        logging.info("Generating and adding captions...")
        try:
            # Create caption images
            caption_images = create_caption_images(story)

            # Add captions to video
            video_with_captions_path = output_path.replace(
                ".mp4", "_with_captions.mp4"
            )
            add_captions_to_video(
                output_path, caption_images, video_with_captions_path
            )

            # Replace the original video with the captioned version
            os.replace(video_with_captions_path, output_path)
            logging.info("Captions added successfully")
        except Exception as e:
            logging.error(f"Error adding captions: {str(e)}")
            # Continue without captions if they fail

        # Verify the output file
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Video file was not created: {output_path}")
        if not os.path.getsize(output_path) > 0:
            raise ValueError(f"Video file is empty: {output_path}")

        logging.info(f"Video created successfully: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Error creating video: {str(e)}")
        raise
