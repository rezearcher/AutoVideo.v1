#!/usr/bin/env python3
"""
Test script for generating a single video with Veo 2.0
"""

import logging
import os
import sys
import time

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("veo-video-test")

def test_veo_video_generation():
    """Test Veo video generation with a minimal prompt"""
    try:
        # Import our veo_adapter
        from app.services.veo_adapter import make_clip
        
        logger.info("Testing Veo video generation...")
        
        # Use a minimal prompt
        prompt = "A beautiful mountain landscape with snow-capped peaks at sunset."
        
        # Try to generate a video
        output_path = make_clip(
            prompt=prompt,
            duration_sec=5,  # Minimal duration
            output_dir="output/test_clips"
        )
        
        if output_path and os.path.exists(output_path):
            logger.info(f"✅ Successfully generated video: {output_path}")
            logger.info(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")
            return True
        else:
            logger.error("❌ Failed to generate video or file not found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during video generation: {e}")
        return False

if __name__ == "__main__":
    # Make sure we're using the correct Python environment
    # by unsetting any problematic environment variables
    os.environ["PYTHONHOME"] = ""
    os.environ["PYTHONPATH"] = ""
    
    # Run the test
    result = test_veo_video_generation()
    sys.exit(0 if result else 1) 