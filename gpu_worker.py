#!/usr/bin/env python3
"""
Standalone GPU Worker for Vertex AI Custom Jobs
Processes video generation tasks with GPU acceleration
"""

import os
import sys
import json
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any
from google.cloud import storage
import tempfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GPUVideoProcessor:
    def __init__(self, project_id: str, bucket_name: str):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(bucket_name)
        
    def check_gpu_availability(self) -> bool:
        """Check if NVIDIA GPU is available"""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("GPU detected successfully")
                logger.info(f"nvidia-smi output:\n{result.stdout}")
                return True
            else:
                logger.error(f"nvidia-smi failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("nvidia-smi not found - no GPU available")
            return False
    
    def download_job_data(self, job_id: str) -> Dict[str, Any]:
        """Download job configuration from GCS"""
        try:
            blob_name = f"jobs/{job_id}/config.json"
            blob = self.bucket.blob(blob_name)
            
            if not blob.exists():
                raise FileNotFoundError(f"Job config not found: {blob_name}")
            
            config_data = json.loads(blob.download_as_text())
            logger.info(f"Downloaded job config for {job_id}")
            return config_data
            
        except Exception as e:
            logger.error(f"Failed to download job data: {e}")
            raise
    
    def upload_result(self, job_id: str, video_path: str, status: str = "completed") -> str:
        """Upload processed video and status to GCS"""
        try:
            # Upload video file
            video_blob_name = f"jobs/{job_id}/output.mp4"
            video_blob = self.bucket.blob(video_blob_name)
            
            with open(video_path, 'rb') as video_file:
                video_blob.upload_from_file(video_file, content_type='video/mp4')
            
            video_url = f"gs://{self.bucket_name}/{video_blob_name}"
            logger.info(f"Uploaded video to: {video_url}")
            
            # Upload status
            status_data = {
                "status": status,
                "video_url": video_url,
                "job_id": job_id,
                "timestamp": str(subprocess.run(['date', '-Iseconds'], capture_output=True, text=True).stdout.strip())
            }
            
            status_blob_name = f"jobs/{job_id}/status.json"
            status_blob = self.bucket.blob(status_blob_name)
            status_blob.upload_from_string(
                json.dumps(status_data, indent=2),
                content_type='application/json'
            )
            
            logger.info(f"Uploaded status to: gs://{self.bucket_name}/{status_blob_name}")
            return video_url
            
        except Exception as e:
            logger.error(f"Failed to upload result: {e}")
            raise
    
    def render_video(self, job_data: Dict[str, Any], output_path: str) -> bool:
        """Render video using GPU acceleration"""
        try:
            logger.info("Starting GPU-accelerated video rendering...")
            
            # Extract job parameters
            script = job_data.get('script', '')
            voice_settings = job_data.get('voice_settings', {})
            video_settings = job_data.get('video_settings', {})
            
            # For now, create a simple test video with GPU acceleration
            # In production, this would use your actual video generation pipeline
            cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'testsrc2=duration=10:size=1920x1080:rate=30',
                '-f', 'lavfi', 
                '-i', 'sine=frequency=1000:duration=10',
                '-c:v', 'h264_nvenc',  # Use NVIDIA GPU encoder
                '-preset', 'fast',
                '-c:a', 'aac',
                '-shortest',
                '-y',  # Overwrite output file
                output_path
            ]
            
            logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("Video rendering completed successfully")
                return True
            else:
                logger.error(f"Video rendering failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Video rendering timed out")
            return False
        except Exception as e:
            logger.error(f"Video rendering error: {e}")
            return False
    
    def process_job(self, job_id: str) -> bool:
        """Main job processing function"""
        try:
            logger.info(f"Processing job: {job_id}")
            
            # Check GPU availability
            if not self.check_gpu_availability():
                logger.error("No GPU available for processing")
                return False
            
            # Download job configuration
            job_data = self.download_job_data(job_id)
            
            # Create temporary output file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                output_path = temp_file.name
            
            try:
                # Render video
                if self.render_video(job_data, output_path):
                    # Upload result
                    self.upload_result(job_id, output_path, "completed")
                    logger.info(f"Job {job_id} completed successfully")
                    return True
                else:
                    # Upload failure status
                    status_data = {
                        "status": "failed",
                        "error": "Video rendering failed",
                        "job_id": job_id
                    }
                    status_blob = self.bucket.blob(f"jobs/{job_id}/status.json")
                    status_blob.upload_from_string(json.dumps(status_data))
                    return False
                    
            finally:
                # Clean up temporary file
                if os.path.exists(output_path):
                    os.unlink(output_path)
                    
        except Exception as e:
            logger.error(f"Job processing failed: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='GPU Video Processing Worker')
    parser.add_argument('--job-id', required=True, help='Job ID to process')
    parser.add_argument('--project-id', required=True, help='GCP Project ID')
    parser.add_argument('--bucket-name', required=True, help='GCS Bucket name')
    
    args = parser.parse_args()
    
    logger.info(f"Starting GPU worker for job: {args.job_id}")
    
    processor = GPUVideoProcessor(args.project_id, args.bucket_name)
    success = processor.process_job(args.job_id)
    
    if success:
        logger.info("Job completed successfully")
        sys.exit(0)
    else:
        logger.error("Job failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 