import argparse
import logging
import os
import sys
import time
import uuid

from google.cloud import storage
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

_MODEL_ID = os.getenv("VEO_MODEL", "veo-3.0-generate-preview")
_BUCKET = os.getenv("VERTEX_BUCKET_NAME")
_TIMEOUT = int(os.getenv("VEO_OP_TIMEOUT", 900))  # 15 min
_LOG = logging.getLogger("veo")

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def make_clip(prompt: str, seconds: int = 8) -> str:
    """Returns a **local** MP4 path — raises on any failure."""
    if not 5 <= seconds <= 8:
        raise ValueError("Veo 3 only supports 5-8 s duration")

    model = GenerativeModel(_MODEL_ID)
    op = model.generate_video_async(
        prompt,
        generation_config=GenerationConfig(
            duration_seconds=seconds,
            aspect_ratio="16:9",
            sample_count=1,  # **required**
            return_raw_tokens=True,  # zero-token smoke probe
        ),
        output_storage=f"gs://{_BUCKET}/veo-temp/",
    )

    _LOG.info("Veo LRO %s started", op.operation.name)
    rsp = op.result(timeout=_TIMEOUT)

    # robust to API structure drift
    uri = getattr(rsp, "videos", [{}])[0].get("gcs_uri") or getattr(
        rsp, "generatedSamples", [{}]
    )[0].get("video", {}).get("uri")
    if not uri:
        raise RuntimeError("No gcs uri in Veo response")

    local = f"/tmp/clip_{uuid.uuid4().hex[:8]}.mp4"
    storage.Client().download_blob_to_file(uri, open(local, "wb"))
    return local


def create_video(prompt: str, output_path: str, duration: int = 8) -> str:
    """Generate a video using Veo and save it to the specified output path."""
    try:
        _LOG.info(f"Generating video for prompt: {prompt}")
        start_time = time.time()
        
        # Generate the video clip
        local_path = make_clip(prompt, duration)
        
        # Copy to output path
        import shutil
        shutil.copy(local_path, output_path)
        
        elapsed = time.time() - start_time
        _LOG.info(f"Video generated successfully in {elapsed:.2f}s: {output_path}")
        
        return output_path
    except Exception as e:
        _LOG.error(f"Error generating video: {e}")
        raise


def main():
    """Main entry point for the Veo adapter when run as a script."""
    parser = argparse.ArgumentParser(description="Generate videos using Veo AI")
    parser.add_argument("--prompt", required=True, help="Text prompt for video generation")
    parser.add_argument("--output", required=True, help="Output path for the generated video")
    parser.add_argument("--duration", type=int, default=8, help="Duration in seconds (5-8)")
    parser.add_argument("--bucket", help="GCS bucket name for Veo output")
    
    args = parser.parse_args()
    
    # Override environment variable if provided
    if args.bucket:
        global _BUCKET
        _BUCKET = args.bucket
    
    if not _BUCKET:
        _LOG.error("VERTEX_BUCKET_NAME environment variable or --bucket argument is required")
        sys.exit(1)
    
    try:
        create_video(args.prompt, args.output, args.duration)
        _LOG.info("Video generation completed successfully")
        sys.exit(0)
    except Exception as e:
        _LOG.error(f"Video generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
