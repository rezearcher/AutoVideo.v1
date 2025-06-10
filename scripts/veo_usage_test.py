#!/usr/bin/env python3
"""
Veo Usage Test - Demonstrates proper usage of Veo with quota awareness

This script generates a test video using the Veo API, respecting rate limits.
"""

import logging
import os
import sys
from pathlib import Path

# Add the root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("veo-test")


def run_test():
    """Run a Veo test with proper quota management"""
    logger.info("Starting Veo usage test...")

    try:
        # Import Veo adapter
        from app.services.veo_adapter import generate_scenes

        # Create simple test prompts
        test_prompts = [
            "A serene mountain landscape with snow-capped peaks at sunset, golden light illuminating",
            "A futuristic city skyline with flying vehicles and neon lights, bustling with activity",
            "A tranquil beach scene with gentle waves lapping at the shore, palm trees swaying",
        ]

        logger.info(f"Generating {len(test_prompts)} test scenes with quota awareness...")

        # Generate scenes with built-in rate limiting
        output_dir = "output/veo_test"
        clip_paths = generate_scenes(test_prompts, output_dir)

        if clip_paths:
            logger.info(f"Successfully generated {len(clip_paths)} clips:")
            for i, path in enumerate(clip_paths):
                logger.info(f"  Clip {i+1}: {path}")

            # Try to concatenate videos if ffmpeg_concat is available
            try:
                from app.services.ffmpeg_concat import ffmpeg_concat

                output_path = "output/veo_test_combined.mp4"
                logger.info(f"Concatenating clips to {output_path}...")

                final_path = ffmpeg_concat(clip_paths, output_path)
                logger.info(f"Final video created at: {final_path}")

            except ImportError:
                logger.warning("ffmpeg_concat not available, skipping concatenation")
        else:
            logger.error("No clips were generated")
            return False

        return True

    except ImportError as e:
        logger.error(f"Required module not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Error during test: {e}")
        return False


if __name__ == "__main__":
    # Make sure the output directory exists
    os.makedirs("output/veo_test", exist_ok=True)

    # Run the test
    success = run_test()

    if success:
        logger.info("✅ Veo test completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Veo test failed")
        sys.exit(1)
