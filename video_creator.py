import json
import logging
import os
import random
import subprocess
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from caption_generator import add_captions_to_video, create_caption_images
from PIL import Image, ImageDraw, ImageFont

# Use our compatibility module instead of direct imports
from app.services.moviepy_compat import (
    MOVIEPY_AVAILABLE,
    AudioFileClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
    resize,
)

# Add new imports for Veo integration
try:
    from google.api_core.exceptions import (
        ResourceExhausted,
        ServiceUnavailable,
        TooManyRequests,
    )
    from google.cloud import storage
    from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

    # Decoupled from MoviePy availability
    VEOAI_AVAILABLE = True
except ImportError:
    VEOAI_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for retries
MAX_RETRIES = 3
MAX_BACKOFF = 120  # Max backoff in seconds


def create_video(images, voiceover_path, story, timestamp, output_path):
    """
    Create a video from images and audio using MoviePy.
    Legacy function kept for backward compatibility.

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
                raise Exception(f"Error creating clip for image {image_path}: {str(e)}")

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

        # Write the initial video file with NVENC hardware encoding
        logging.info(f"Writing initial video to: {output_path}")
        try:
            final_clip.write_videofile(
                output_path,
                fps=24,
                codec="libx264",
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
        except Exception as e:
            # Fallback to CPU encoding if hardware acceleration fails
            logger.warning(f"Hardware encoding failed, falling back to CPU: {str(e)}")
            final_clip.write_videofile(
                output_path,
                fps=24,
                codec="libx264",
                audio_codec="aac",
            )

        # Generate and add captions
        logging.info("Generating and adding captions...")
        try:
            # Create caption images
            caption_images = create_caption_images(story)

            # Add captions to video
            video_with_captions_path = output_path.replace(".mp4", "_with_captions.mp4")
            add_captions_to_video(output_path, caption_images, video_with_captions_path)

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


def make_veo_clip(
    prompt: str,
    duration_sec: int = 8,
    aspect: str = "16:9",
    output_dir: str = None,
    bucket: str = os.environ.get("VERTEX_BUCKET_NAME", ""),
    retries: int = MAX_RETRIES,
) -> str:
    """
    Generate a video clip using Google's Veo 3 AI with retry logic.
    Now uses the veo_adapter module for better error handling.

    Args:
        prompt (str): Detailed prompt for video generation
        duration_sec (int): Duration in seconds (must be 5-8s for Veo 3)
        aspect (str): Aspect ratio (16:9 is the only supported ratio for Veo 3)
        output_dir (str): Directory to save the video (default: "output/veo_clips")
        bucket (str): GCS bucket to store temporary files
        retries (int): Maximum number of retry attempts

    Returns:
        str: Path to the generated video clip
    """
    if not VEOAI_AVAILABLE:
        raise ImportError(
            "Vertex AI Video Generation (Veo) is not available. Install required packages."
        )

    # Validate duration (Veo 3 only supports 5-8 seconds)
    if duration_sec not in range(5, 9):
        raise ValueError("Veo 3 only supports 5-8 second videos")

    # Ensure we have a bucket configured
    if not bucket:
        raise ValueError(
            "No GCS bucket configured. Set VERTEX_BUCKET_NAME environment variable."
        )

    logger.info(f"Generating Veo video clip with prompt: {prompt[:100]}...")

    # Set default output directory if not provided
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "output", "veo_clips")
    os.makedirs(output_dir, exist_ok=True)

    # Try using the adapter module first
    try:
        from app.services.veo_adapter import make_clip

        # Use the adapter to generate the clip
        local_path = make_clip(prompt, seconds=duration_sec)

        # Move the temp file to the output directory with a descriptive name
        clip_name = f"veo_clip_{uuid4().hex[:8]}.mp4"
        final_path = os.path.join(output_dir, clip_name)
        os.rename(local_path, final_path)

        logger.info(f"Veo clip generated and saved to {final_path}")
        return final_path

    except ImportError:
        logger.warning(
            "Veo adapter not available, falling back to direct implementation"
        )
        # Calculate max wait time for exponential backoff
        max_wait_time = min(MAX_BACKOFF, 2 ** (retries - 1) * 15)

        for attempt in range(retries):
            try:
                # Initialize the Veo model
                from vertexai.preview.generative_models import (
                    GenerationConfig,
                    GenerativeModel,
                )

                model = GenerativeModel("veo-3.0-generate-preview")

                # Generate the video using async LRO pattern
                logger.info(
                    f"Requesting {duration_sec}s video with aspect ratio {aspect} (attempt {attempt+1}/{retries})..."
                )
                start_time = time.time()

                # Launch async operation
                operation = model.generate_video_async(
                    prompt=prompt,
                    generation_config=GenerationConfig(
                        duration_seconds=duration_sec,
                        aspect_ratio=aspect,
                        sample_count=1,  # Must be explicitly set per Google docs
                    ),
                    output_storage=f"gs://{bucket}/veo-temp/",
                )

                # Poll for result with timeout (15 minutes max)
                logger.info(
                    "Video generation operation started, waiting for completion..."
                )
                response = operation.result(timeout=900)  # 15 minute timeout

                generation_time = time.time() - start_time
                logger.info(f"Video generated in {generation_time:.1f}s")

                # Get GCS URI from response
                gcs_uri = None
                if hasattr(response, "videos") and response.videos:
                    gcs_uri = response.videos[0].gcs_uri
                elif (
                    hasattr(response, "generatedSamples") and response.generatedSamples
                ):
                    sample = response.generatedSamples[0]
                    if hasattr(sample, "video") and sample.video:
                        gcs_uri = sample.video.uri

                if not gcs_uri:
                    raise ValueError("No video URI found in response")

                logger.info(f"Video available at: {gcs_uri}")

                # Download the video from GCS
                from google.cloud import storage

                storage_client = storage.Client()

                # Parse the URI to get bucket and blob path
                # Format: gs://bucket-name/path/to/object
                gcs_path = gcs_uri.replace("gs://", "")
                bucket_name, blob_path = gcs_path.split("/", 1)

                # Get the bucket and blob
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_path)

                # Download to a temporary file
                clip_name = f"veo_clip_{uuid4().hex[:8]}.mp4"
                local_path = os.path.join(output_dir, clip_name)
                blob.download_to_filename(local_path)

                logger.info(f"Downloaded video to {local_path}")
                return local_path

            except (ResourceExhausted, ServiceUnavailable, TooManyRequests) as e:
                if attempt < retries - 1:
                    wait_time = min(max_wait_time, 2**attempt * 15)
                    logger.warning(
                        f"Rate limit or service unavailable ({str(e)}). Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed after {retries} attempts: {str(e)}")
                    raise
            except Exception as e:
                logger.error(f"Error generating video: {str(e)}")
                raise


def enhance_story_for_video_scenes(
    story: str, num_scenes: int = 5
) -> List[Dict[str, str]]:
    """
    Transform a story into a series of video scene prompts.

    Args:
        story (str): The original story
        num_scenes (int): Number of scenes to generate

    Returns:
        List[Dict[str, str]]: List of scene dictionaries with prompts and camera instructions
    """
    scenes = []

    # Generate scene prompts using OpenAI or directly from the story
    try:
        from story_generator import call_openai_with_backoff

        prompt = f"""
        Given this story, create exactly {num_scenes} detailed cinematic scene prompts that capture key moments.
        
        For each scene, include:
        1. A specific camera movement (dolly, pan, tilt, crane, steadicam)
        2. Lighting description (warm, cool, golden hour, moody, etc.)
        3. Specific visual elements to include
        4. A single short line of dialogue (EXACTLY 7 WORDS OR FEWER) if appropriate
        5. Style/mood description
        
        IMPORTANT: Dialogue MUST be 7 words or fewer. This is a strict technical limitation.
        
        Format as a JSON array of objects with these properties: "scene_description", "camera", "lighting", "dialogue", "style"
        
        Story: {story}
        """

        response = call_openai_with_backoff(
            max_retries=3,
            max_time=60,
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert cinematographer who creates detailed, Veo-optimized scene prompts. Format your output strictly as valid JSON, nothing else. All dialogue MUST be 7 words or fewer.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        scenes_data = json.loads(response.choices[0].message.content)
        scenes = scenes_data.get("scenes", [])

        # Ensure we have valid scene data
        if not scenes or not isinstance(scenes, list):
            raise ValueError("Failed to generate valid scene data")

        # Enforce dialogue length limit
        for scene in scenes:
            if scene.get("dialogue"):
                # Count words and truncate if needed
                words = scene["dialogue"].split()
                if len(words) > 7:
                    scene["dialogue"] = " ".join(words[:7])
                    logger.warning(
                        f"Truncated dialogue to 7 words: {scene['dialogue']}"
                    )

    except Exception as e:
        logger.warning(f"Error generating enhanced scene prompts: {str(e)}")
        logger.info("Falling back to basic scene generation")

        # Simple fallback approach - split the story into chunks
        paragraphs = [p.strip() for p in story.split("\n") if p.strip()]

        # If we don't have enough paragraphs, use the whole story for each scene
        if len(paragraphs) < num_scenes:
            paragraphs = [story] * num_scenes

        # Select evenly distributed paragraphs if we have more than needed
        if len(paragraphs) > num_scenes:
            step = len(paragraphs) // num_scenes
            paragraphs = [paragraphs[i * step] for i in range(num_scenes)]

        # Create basic scene dictionaries
        scenes = []
        for i, paragraph in enumerate(paragraphs[:num_scenes]):
            camera_moves = [
                "slow dolly-in",
                "gentle pan right",
                "static wide shot",
                "crane down",
                "tracking shot",
                "medium close-up",
            ]
            lighting = [
                "natural daylight",
                "warm sunset glow",
                "cool blue moonlight",
                "dramatic side lighting",
                "soft diffused light",
            ]
            styles = [
                "cinematic 4K",
                "film noir",
                "vibrant documentary",
                "dramatic feature film",
                "intimate portrait",
            ]

            scenes.append(
                {
                    "scene_description": paragraph[:200],  # Limit length
                    "camera": camera_moves[i % len(camera_moves)],
                    "lighting": lighting[i % len(lighting)],
                    "dialogue": "",  # No dialogue in fallback mode
                    "style": styles[i % len(styles)],
                }
            )

    # Format each scene for Veo prompt
    formatted_scenes = []
    for i, scene in enumerate(scenes):
        veo_prompt = f"""
        A cinematic 8-second shot of {scene['scene_description']}.
        Camera: {scene['camera']}, 35 mm lens, f/2.8 bokeh.
        Lighting: {scene['lighting']}.
        """

        # Only add dialogue if it exists, isn't empty, and is within length limit
        if scene.get("dialogue") and len(scene["dialogue"]) > 0:
            # Double-check dialogue length (≤7 words)
            words = scene["dialogue"].split()
            if len(words) <= 7:
                veo_prompt += f"Audio: ambient sounds, one line of dialogue: \"{scene['dialogue']}\". "
            else:
                # Truncate if somehow it's still too long
                dialogue = " ".join(words[:7])
                veo_prompt += (
                    f'Audio: ambient sounds, one line of dialogue: "{dialogue}". '
                )
        else:
            veo_prompt += "Audio: ambient sounds that match the scene. "

        veo_prompt += f"Style: {scene['style']}, 24 fps, natural color grading."

        formatted_scenes.append({"raw_scene": scene, "veo_prompt": veo_prompt.strip()})

    return formatted_scenes


def generate_scene_videos(scenes: List[Dict[str, str]], output_dir: str) -> List[str]:
    """
    Generate videos for each scene using Veo.

    Args:
        scenes (List[Dict[str, str]]): List of scene dictionaries with prompts
        output_dir (str): Directory to save the videos

    Returns:
        List[str]: List of paths to the generated videos
    """
    video_paths = []

    for i, scene in enumerate(scenes):
        logger.info(f"Generating video for scene {i+1}/{len(scenes)}")
        try:
            video_path = make_veo_clip(
                prompt=scene["veo_prompt"],
                duration_sec=8,  # 8 seconds is the max for preview
                aspect="16:9",
                output_dir=output_dir,
            )
            video_paths.append(video_path)
            logger.info(f"Scene {i+1} video generated: {video_path}")
        except Exception as e:
            logger.error(f"Error generating video for scene {i+1}: {str(e)}")
            # Continue with remaining scenes

    return video_paths


def ffmpeg_concat(
    video_paths: List[str],
    output_path: str,
    crossfade: bool = True,
    color_grade: bool = True,
    normalize_audio: bool = True,
) -> str:
    """
    Concatenate multiple videos using FFmpeg with optional crossfade, color grading, and audio normalization.

    Args:
        video_paths (List[str]): List of video file paths
        output_path (str): Output video path
        crossfade (bool): Whether to add crossfade transitions
        color_grade (bool): Apply color grading for more vibrant output
        normalize_audio (bool): Apply audio loudness normalization

    Returns:
        str: Path to the concatenated video
    """
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")

    if len(video_paths) == 1:
        # If only one video, just copy it to intermediate
        import shutil

        intermediate_path = output_path.replace(".mp4", "_intermediate.mp4")
        shutil.copy(video_paths[0], intermediate_path)
    else:
        # Create output directory if needed
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Intermediate file for the concatenated result
        intermediate_path = output_path.replace(".mp4", "_intermediate.mp4")

        if crossfade:
            # With crossfade - more complex command using xfade filter
            crossfade_duration = 0.5  # half-second crossfade

            # Generate a complex filter string for crossfades
            filter_complex = ""
            for i in range(len(video_paths) - 1):
                # For each video except the last one
                if i == 0:
                    # First video
                    filter_complex += f"[0:v][0:a]"

                # Add crossfade filter
                next_idx = i + 1
                filter_complex += f"[{next_idx}:v][{next_idx}:a]xfade=transition=fade:duration={crossfade_duration}:offset={7.5-crossfade_duration}"

                if i < len(video_paths) - 2:
                    # Not the last crossfade, add a label
                    filter_complex += f"[v{i}][a{i}];"
                    filter_complex += f"[v{i}][a{i}]"

            # Complete the filter
            filter_complex += "[outv][outa]"

            # Build the FFmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if it exists
            ]

            # Add input files
            for video_path in video_paths:
                cmd.extend(["-i", video_path])

            # Add filter complex and output
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[outv]",
                    "-map",
                    "[outa]",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "23",
                    "-preset",
                    "medium",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    intermediate_path,
                ]
            )
        else:
            # Without crossfade - simpler concatenation
            # Create a temporary file listing all videos
            concat_file = os.path.join(os.path.dirname(output_path), "concat_list.txt")
            with open(concat_file, "w") as f:
                for video_path in video_paths:
                    f.write(f"file '{os.path.abspath(video_path)}'\n")

            # Build the FFmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if it exists
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_file,
                "-c",
                "copy",  # Just copy streams without re-encoding
                intermediate_path,
            ]

        # Execute the command
        logger.info(f"Executing FFmpeg concat: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)

        # Check for errors
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr}")
            raise RuntimeError(f"FFmpeg failed with exit code {process.returncode}")

        # Clean up concat file if it exists
        if not crossfade and os.path.exists(concat_file):
            os.remove(concat_file)

    # Apply color grading if requested
    if color_grade:
        color_graded_path = output_path.replace(".mp4", "_graded.mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            intermediate_path,
            "-vf",
            "eq=saturation=1.2:contrast=1.05",  # Color grading
            "-c:a",
            "copy",  # Copy audio without re-encoding
            color_graded_path,
        ]

        logger.info(f"Applying color grading: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode != 0:
            logger.warning(
                f"Color grading failed, using ungraded video: {process.stderr}"
            )
            color_graded_path = intermediate_path
        else:
            # Remove intermediate file if color grading succeeded
            if os.path.exists(intermediate_path):
                os.remove(intermediate_path)
    else:
        color_graded_path = intermediate_path

    # Apply audio normalization if requested
    if normalize_audio:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            color_graded_path,
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",  # Audio normalization
            output_path,
        ]

        logger.info(f"Applying audio normalization: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode != 0:
            logger.warning(
                f"Audio normalization failed, using unnormalized audio: {process.stderr}"
            )
            # If normalization fails, just copy the color-graded video
            import shutil

            shutil.copy(color_graded_path, output_path)
        else:
            # Remove color-graded intermediate if normalization succeeded
            if (
                os.path.exists(color_graded_path)
                and color_graded_path != intermediate_path
            ):
                os.remove(color_graded_path)
    else:
        # If not normalizing, just rename/copy the color-graded video
        import shutil

        shutil.copy(color_graded_path, output_path)

        # Clean up intermediate files
        if os.path.exists(color_graded_path) and color_graded_path != output_path:
            os.remove(color_graded_path)

    logger.info(f"Videos successfully concatenated and processed to: {output_path}")
    return output_path


def create_veo_video(story: str, output_path: str, num_scenes: int = 5) -> str:
    """
    Create a complete video using Veo from a story.
    Uses the new scene_splitter module for more reliable scene generation.

    Args:
        story (str): The story text
        output_path (str): Path to save the final video
        num_scenes (int): Number of scenes to generate

    Returns:
        str: Path to the generated video
    """
    try:
        # Create output directory
        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)

        # Create a scenes directory
        scenes_dir = os.path.join(output_dir, "scenes")
        os.makedirs(scenes_dir, exist_ok=True)

        # Step 1: Transform story into scene prompts
        logger.info(f"Creating {num_scenes} scene prompts from story...")

        # Try to use the new scene splitter module first
        try:
            from app.services.scene_splitter import split_into_scenes

            scene_prompts = split_into_scenes(story, max_scenes=num_scenes)
            scenes = [{"veo_prompt": prompt} for prompt in scene_prompts]
            logger.info(f"Generated {len(scenes)} scene prompts using scene_splitter")
        except ImportError:
            # Fall back to original method if module not available
            logger.info("Scene splitter not available, using legacy scene enhancement")
            scenes = enhance_story_for_video_scenes(story, num_scenes)

        # Step 2: Generate videos for each scene
        logger.info("Generating individual scene videos...")
        video_paths = []

        for i, scene in enumerate(scenes):
            logger.info(f"Generating video for scene {i+1}/{len(scenes)}")
            try:
                prompt = scene["veo_prompt"] if "veo_prompt" in scene else scene
                video_path = make_veo_clip(
                    prompt=prompt,
                    duration_sec=(
                        8 if i < len(scenes) - 1 else 5
                    ),  # Last clip is shorter
                    aspect="16:9",
                    output_dir=scenes_dir,
                )
                video_paths.append(video_path)
                logger.info(f"Scene {i+1} video generated: {video_path}")
            except Exception as e:
                logger.error(f"Error generating video for scene {i+1}: {str(e)}")
                # Continue with remaining scenes

        if not video_paths:
            raise ValueError("No scene videos were generated")

        # Step 3: Concatenate videos
        logger.info("Concatenating scene videos into final video...")
        final_path = ffmpeg_concat(
            video_paths,
            output_path,
            crossfade=True,
            color_grade=True,
            normalize_audio=False,  # Veo clips don't have audio to normalize
        )

        logger.info(f"Final video created: {final_path}")
        return final_path

    except Exception as e:
        logger.error(f"Error creating Veo video: {str(e)}")
        raise
