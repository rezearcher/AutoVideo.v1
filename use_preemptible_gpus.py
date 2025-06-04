#!/usr/bin/env python3
"""
Example script demonstrating how to use preemptible GPUs with AutoVideo

This script shows how to use the PreemptibleGPUManager to run video generation
jobs with preemptible GPUs, which are ~70% cheaper but can be terminated by GCP
at any time. The manager automatically handles retries if instances are preempted.
"""

import argparse
import logging
import os
import sys
from dotenv import load_dotenv

from preemptible_gpu_manager import PreemptibleGPUManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Run AutoVideo with preemptible GPUs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--topic", 
        type=str, 
        required=True,
        help="Topic to generate a video about"
    )
    
    parser.add_argument(
        "--preemptible", 
        action="store_true",
        help="Use preemptible GPUs (cheaper but may be terminated)"
    )
    
    parser.add_argument(
        "--max-retries", 
        type=int, 
        default=5,
        help="Maximum number of retries if preempted"
    )
    
    parser.add_argument(
        "--retry-delay", 
        type=int, 
        default=30,
        help="Delay in seconds between retry attempts"
    )
    
    parser.add_argument(
        "--region", 
        type=str, 
        default="us-central1",
        help="GCP region to use for GPU instances"
    )
    
    return parser.parse_args()


def generate_video_with_preemptible_gpus(
    topic, 
    use_preemptible=True, 
    max_retries=5, 
    retry_delay=30,
    region="us-central1"
):
    """
    Generate a video using preemptible GPUs with automatic retry.
    
    Args:
        topic: Topic to generate a video about
        use_preemptible: Whether to use preemptible GPUs
        max_retries: Maximum number of retries if preempted
        retry_delay: Delay in seconds between retry attempts
        region: GCP region to use for GPU instances
    """
    # Get project ID from environment
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is not set")
        return False
    
    logger.info(f"🚀 Generating video about '{topic}' with {'preemptible' if use_preemptible else 'standard'} GPUs")
    
    try:
        # Initialize the PreemptibleGPUManager
        manager = PreemptibleGPUManager(
            project_id=project_id,
            region=region,
            max_retries=max_retries,
            retry_delay=retry_delay
        )
        
        # Modify the vertex configurations to include preemptible options
        manager.modify_vertex_configs_for_preemptible()
        
        # This is a simplified example. In a real implementation,
        # you would need to:
        # 1. Generate a story about the topic
        # 2. Generate images for the story
        # 3. Generate audio narration
        # Then pass these to the create_video_job_with_retry method
        
        # For this example, we'll just assume these steps have been done
        # and simulate with placeholder values
        image_paths = ["placeholder_image_path.jpg"]
        audio_path = "placeholder_audio_path.mp3"
        story = f"This is a story about {topic}."
        
        # Create and submit the job
        job_id = manager.create_video_job_with_retry(
            image_paths=image_paths,
            audio_path=audio_path,
            story=story,
            use_preemptible=use_preemptible
        )
        
        logger.info(f"✅ Job submitted successfully with ID: {job_id}")
        
        # Wait for the job to complete with automatic retry on preemption
        logger.info(f"⏳ Waiting for job {job_id} to complete (with automatic retry if preempted)...")
        result = manager.wait_for_job_with_retry(job_id)
        
        if result.get("status") == "SUCCEEDED":
            logger.info(f"✅ Job completed successfully: {job_id}")
            
            # Download the result
            output_path = f"output_video_{job_id}.mp4"
            if manager.vertex_service.download_video_result(job_id, output_path):
                logger.info(f"📥 Video downloaded to: {output_path}")
            else:
                logger.error(f"❌ Failed to download video for job: {job_id}")
                
            return True
        else:
            logger.error(f"❌ Job failed: {result}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error generating video: {str(e)}")
        return False


def main():
    """Main function"""
    args = parse_args()
    
    logger.info(f"Starting AutoVideo with {'preemptible' if args.preemptible else 'standard'} GPUs")
    logger.info(f"Topic: {args.topic}")
    logger.info(f"Max retries: {args.max_retries}")
    logger.info(f"Retry delay: {args.retry_delay}s")
    logger.info(f"Region: {args.region}")
    
    success = generate_video_with_preemptible_gpus(
        topic=args.topic,
        use_preemptible=args.preemptible,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        region=args.region
    )
    
    if success:
        logger.info("✅ Video generation completed successfully")
        return 0
    else:
        logger.error("❌ Video generation failed")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 