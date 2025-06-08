"""Worker for processing video scene generation requests from Pub/Sub."""

import base64
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import flask

# Add project root to path to allow imports
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.config import settings
from app.config.storage import get_storage_path
from app.services.storage_service import StorageService
from app.services.veo_service import VeoService

logger = logging.getLogger(__name__)

# Initialize services
storage_service = StorageService()
veo_service = VeoService(storage_service)

app = flask.Flask(__name__)


@app.route("/", methods=["POST"])
def process_scene_request():
    """
    Process a Pub/Sub message containing a scene generation request.

    Expected message format:
    {
        "scene_id": "unique_scene_id",
        "prompt": "Scene description prompt",
        "params": {
            "duration_seconds": 5,
            "aspect_ratio": "16:9",
            "reference_image_path": "gs://bucket/path/to/image.jpg" (optional)
        }
    }
    """
    # Get the message data
    envelope = flask.request.get_json()

    if not envelope:
        return "No Pub/Sub message received", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        return "Invalid Pub/Sub message format", 400

    # Extract the message
    pubsub_message = envelope["message"]

    if not pubsub_message.get("data"):
        return "Empty Pub/Sub message", 204

    # Decode the message data
    try:
        data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
        message = json.loads(data)
    except Exception as e:
        logger.error(f"Error decoding message: {e}")
        return "Error decoding message", 400

    # Extract the scene information
    scene_id = message.get("scene_id")
    prompt = message.get("prompt")
    params = message.get("params", {})

    if not scene_id or not prompt:
        return "Missing required fields: scene_id and prompt", 400

    # Extract parameters
    duration_seconds = params.get("duration_seconds", 5)
    aspect_ratio = params.get("aspect_ratio", "16:9")
    reference_image_path = params.get("reference_image_path")

    # Download reference image to local path if provided
    local_ref_image = None
    if reference_image_path and reference_image_path.startswith("gs://"):
        try:
            # Extract bucket and object path
            parts = reference_image_path.replace("gs://", "").split("/", 1)
            if len(parts) == 2:
                bucket_name, object_path = parts
                local_ref_image = f"/tmp/ref_{uuid.uuid4().hex[:8]}.jpg"
                storage_service.download_from_gcs(
                    bucket_name, object_path, local_ref_image
                )
                logger.info(f"Downloaded reference image to {local_ref_image}")
        except Exception as e:
            logger.error(f"Error downloading reference image: {e}")
            # Continue without reference image

    # Generate the video
    logger.info(f"Generating scene {scene_id} with prompt: {prompt}")

    try:
        video_url = veo_service.generate_video(
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            reference_image_path=local_ref_image,
        )

        if not video_url:
            logger.error(f"Failed to generate video for scene {scene_id}")
            return "Video generation failed", 500

        # Save the URL to a known location for the parent process to find
        clip_path = get_storage_path("videos", "clips", f"{scene_id}.mp4")

        # Download the video from the Veo storage path and re-upload to clips path
        local_path = f"/tmp/{scene_id}.mp4"
        storage_service.download_file(video_url, local_path)

        final_url = storage_service.upload_file(local_path, clip_path)

        # Clean up temporary files
        if os.path.exists(local_path):
            os.remove(local_path)

        if local_ref_image and os.path.exists(local_ref_image):
            os.remove(local_ref_image)

        return (
            json.dumps({"success": True, "scene_id": scene_id, "video_url": final_url}),
            200,
        )

    except Exception as e:
        logger.error(f"Error processing scene {scene_id}: {e}")
        return f"Error processing scene: {e}", 500


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get port from environment variable or default to 8080
    port = int(os.environ.get("PORT", 8080))

    # Run the Flask app
    app.run(host="0.0.0.0", port=port)
