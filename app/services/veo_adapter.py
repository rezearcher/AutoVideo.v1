"""
Veo Adapter - Simplified interface for Google's Veo AI video generation
"""

import logging
import os
import time
from typing import List
from uuid import uuid4

from google.api_core.exceptions import ResourceExhausted, TooManyRequests
from google.cloud import storage
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

# Configure logging
logger = logging.getLogger(__name__)

# Constants
VEO_MODEL = os.environ.get("VEO_MODEL", "veo-2.0-generate-001")
VERTEX_BUCKET_NAME = os.environ.get("VERTEX_BUCKET_NAME")
DEFAULT_DURATION = 8
TOKEN_LIMIT_PER_MIN = 10

# Cache for token usage
_token_usage = {"used_this_minute": 0, "last_reset": time.time()}


def _reset_token_usage_if_needed():
    """Reset token usage counter if a minute has passed"""
    now = time.time()
    if now - _token_usage["last_reset"] > 60:  # 60 seconds in a minute
        _token_usage["used_this_minute"] = 0
        _token_usage["last_reset"] = now
        logger.info("Reset Veo token usage counter")


def _wait_for_tokens(tokens_needed: int):
    """Wait if token limit would be exceeded"""
    _reset_token_usage_if_needed()

    # Check if we have enough tokens
    while _token_usage["used_this_minute"] + tokens_needed > TOKEN_LIMIT_PER_MIN:
        wait_time = 60 - (time.time() - _token_usage["last_reset"])
        if wait_time > 0:
            logger.info(f"Token limit reached. Waiting {wait_time:.1f}s for reset.")
            time.sleep(min(wait_time + 1, 60))  # Wait until next minute
        _reset_token_usage_if_needed()


def make_clip(
    prompt: str,
    duration_sec: int = DEFAULT_DURATION,
    output_dir: str = None,
    return_raw_tokens: bool = False,
) -> str:
    """
    Generate a video clip using Google's Veo AI.

    Args:
        prompt (str): Detailed prompt for video generation
        duration_sec (int): Duration in seconds (must be 5-8s for Veo 3)
        output_dir (str): Directory to save the video (default: "output/veo_clips")
        return_raw_tokens (bool): If True, return a zero-token response for diagnostics

    Returns:
        str: Path to the generated video clip
    """
    # Validate inputs
    if not (5 <= duration_sec <= 8):
        logger.warning(
            f"Duration {duration_sec}s outside optimal 5-8s range. Adjusting to 8s."
        )
        duration_sec = 8

    if not output_dir:
        output_dir = "output/veo_clips"
    os.makedirs(output_dir, exist_ok=True)

    clip_id = f"veo_{uuid4().hex[:8]}"
    output_path = f"{output_dir}/{clip_id}.mp4"

    # For diagnostic mode, return immediately
    if return_raw_tokens:
        logger.info("Diagnostic mode: Veo connection successful")
        # Zero token operations for diagnostics
        model = GenerativeModel(VEO_MODEL)
        generation_config = GenerationConfig(temperature=0.4)
        return "diagnostic_success"

    # Maximum retry attempts for quota-related errors
    max_attempts = 5
    backoff_factor = 2

    for attempt in range(max_attempts):
        try:
            # Check if we have enough tokens before proceeding
            tokens_needed = (
                1  # Count each request as 1 token since we're limited by requests/min
            )
            _wait_for_tokens(tokens_needed)

            # Initialize the model
            model = GenerativeModel(VEO_MODEL)

            # Create generation config
            generation_config = GenerationConfig(
                temperature=0.4,  # Lower temperature for more predictable results
                max_output_tokens=8192,
            )

            # Full prompt template
            full_prompt = f"""
            Create a high-quality, cinematic video clip that's exactly {duration_sec} seconds long.
            
            Scene description:
            {prompt}
            
            Make it visually stunning with realistic lighting, depth of field, and camera movement.
            The style should be photorealistic and cinematic.
            """

            # Log the request
            logger.info(f"Generating Veo clip: {clip_id} - Duration: {duration_sec}s")
            logger.info(f"Prompt: {prompt[:100]}...")

            # Generate the video
            start_time = time.time()
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config,
                stream=False,
            )

            # Update token usage
            _token_usage["used_this_minute"] += tokens_needed

            # Process the response
            if hasattr(response, "candidates") and response.candidates:
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "video") and part.video:
                            # Save the video to the specified path
                            with open(output_path, "wb") as f:
                                f.write(part.video.data)

                            generation_time = time.time() - start_time
                            logger.info(
                                f"✅ Veo clip generated in {generation_time:.1f}s: {output_path}"
                            )
                            return output_path

            # If we get here, the response didn't contain a video
            raise ValueError("Veo response didn't contain video data")

        except (ResourceExhausted, TooManyRequests) as e:
            logger.warning(
                f"Veo API quota error (attempt {attempt+1}/{max_attempts}): {str(e)}"
            )
            # Update for longer wait on quota issues
            _token_usage["used_this_minute"] = TOKEN_LIMIT_PER_MIN

            if attempt < max_attempts - 1:
                # Calculate exponential backoff time
                wait_time = 60 * (backoff_factor**attempt)  # Exponential backoff
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                logger.error(
                    f"Failed after {max_attempts} attempts due to quota limits."
                )
                raise

        except Exception as e:
            logger.error(f"Error generating Veo clip: {str(e)}")
            raise


def generate_scenes(
    prompts: List[str], output_dir: str = None, parallel: bool = False
) -> List[str]:
    """
    Generate multiple video clips for different scenes.

    Args:
        prompts (List[str]): List of scene prompts
        output_dir (str): Directory to save videos
        parallel (bool): If True, generate clips in parallel (not implemented yet)

    Returns:
        List[str]: Paths to generated clips
    """
    if not output_dir:
        output_dir = f"output/veo_clips_{uuid4().hex[:8]}"

    os.makedirs(output_dir, exist_ok=True)
    clip_paths = []

    # For now, just process sequentially
    for i, prompt in enumerate(prompts):
        logger.info(f"Generating scene {i+1}/{len(prompts)}")

        # Try multiple times with exponential backoff for quota errors
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                clip_path = make_clip(prompt, DEFAULT_DURATION, output_dir)
                clip_paths.append(clip_path)
                logger.info(f"Successfully generated clip for scene {i+1}")
                break  # Success, exit retry loop
            except (ResourceExhausted, TooManyRequests) as e:
                if attempt < max_attempts - 1:
                    # If not the last attempt, wait and retry
                    wait_time = 120 * (attempt + 1)  # Longer wait (was 60s)
                    logger.warning(
                        f"Quota exceeded for scene {i+1}. Waiting {wait_time}s before retry..."
                    )
                    time.sleep(wait_time)
                else:
                    # Last attempt failed, log and continue to next scene
                    logger.error(
                        f"Failed to generate scene {i+1} after {max_attempts} attempts: {e}"
                    )
            except Exception as e:
                logger.error(f"Failed to generate scene {i+1}: {str(e)}")
                break  # Non-quota error, don't retry

        # Always add a pause between scenes to avoid hitting quotas too quickly
        if i < len(prompts) - 1:  # No need to wait after the last scene
            pause_time = 30  # Increased from 15 to 30 seconds
            logger.info(
                f"Pausing for {pause_time}s between scenes to respect quota limits..."
            )
            time.sleep(pause_time)

    return clip_paths
