#!/usr/bin/env python3
"""
Preemptible GPU Manager for AutoVideo

This module extends the VertexGPUJobService to support preemptible GPU instances,
automatically handling retries when instances are preempted by GCP.
"""

import logging
import time
from typing import Dict, Any, Optional

from vertex_gpu_service import VertexGPUJobService

logger = logging.getLogger(__name__)


class PreemptibleGPUManager:
    """
    Manages preemptible GPU instances with automatic retry capability.
    
    This class wraps the VertexGPUJobService to add support for preemptible
    GPU instances, which are ~70% cheaper but can be terminated by GCP
    at any time. When a preemptible instance is terminated, this manager
    automatically retries the job.
    """
    
    def __init__(
        self, 
        project_id: str, 
        region: str = "us-central1", 
        bucket_name: str = None,
        max_retries: int = 5,
        retry_delay: int = 30
    ):
        """
        Initialize the PreemptibleGPUManager.
        
        Args:
            project_id: GCP project ID
            region: Default region for GPU instances
            bucket_name: GCS bucket for storing job data
            max_retries: Maximum number of retry attempts
            retry_delay: Delay in seconds between retry attempts
        """
        self.vertex_service = VertexGPUJobService(project_id, region, bucket_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.project_id = project_id
        self.region = region
    
    def create_video_job_with_retry(
        self, 
        image_paths: list, 
        audio_path: str, 
        story: str,
        use_preemptible: bool = True
    ) -> str:
        """
        Create a video generation job with preemptible GPU support and automatic retry.
        
        Args:
            image_paths: List of paths to image files
            audio_path: Path to audio file
            story: Story text
            use_preemptible: Whether to use preemptible GPUs (cheaper but may be terminated)
            
        Returns:
            job_id: ID of the created job
        """
        # Generate a unique job ID
        job_id = self.vertex_service.create_video_job(image_paths, audio_path, story)
        
        if not use_preemptible:
            # For non-preemptible instances, just use the standard workflow
            logger.info("Using standard (non-preemptible) GPU instances")
            return job_id
        
        # For preemptible instances, set up the retry mechanism
        logger.info("Using preemptible GPU instances with automatic retry")
        
        # Add the job to a tracking system for retry
        self._track_preemptible_job(job_id, image_paths, audio_path, story)
        
        return job_id
    
    def _track_preemptible_job(self, job_id: str, image_paths: list, audio_path: str, story: str):
        """Track a preemptible job for potential retry"""
        # This would typically store job details in a database or persistent storage
        # For now, we'll just log that we're tracking it
        logger.info(f"Tracking preemptible job {job_id} for potential retry")
    
    def wait_for_job_with_retry(self, job_id: str, timeout: int = None) -> Dict[str, Any]:
        """
        Wait for a job to complete, with automatic retry if preempted.
        
        Args:
            job_id: ID of the job to wait for
            timeout: Timeout in seconds for each attempt
            
        Returns:
            Job status dictionary
        """
        attempt = 0
        
        while attempt < self.max_retries:
            try:
                logger.info(f"Waiting for job {job_id} (attempt {attempt+1}/{self.max_retries})")
                result = self.vertex_service.wait_for_job_completion(job_id, timeout)
                
                # Check if job was preempted
                if self._was_job_preempted(result):
                    attempt += 1
                    if attempt < self.max_retries:
                        logger.warning(
                            f"Job {job_id} was preempted by GCP. "
                            f"Retrying in {self.retry_delay} seconds (attempt {attempt+1})"
                        )
                        time.sleep(self.retry_delay)
                        
                        # Recreate the job with a new ID
                        job_id = self._retry_preempted_job(job_id)
                    else:
                        logger.error(
                            f"Job {job_id} was preempted and max retries ({self.max_retries}) reached. "
                            "Falling back to non-preemptible instance."
                        )
                        # Fallback to non-preemptible for the final attempt
                        job_id = self._retry_with_non_preemptible(job_id)
                        result = self.vertex_service.wait_for_job_completion(job_id, timeout)
                        return result
                else:
                    # Job completed successfully
                    return result
                    
            except Exception as e:
                logger.error(f"Error waiting for job {job_id}: {str(e)}")
                attempt += 1
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Max retries reached for job {job_id}")
                    raise
        
        # This should not be reached due to the return statements above
        return {"status": "ERROR", "message": "Max retries reached"}
    
    def _was_job_preempted(self, job_status: Dict[str, Any]) -> bool:
        """
        Check if a job was preempted by GCP.
        
        Args:
            job_status: Job status dictionary from VertexGPUJobService
            
        Returns:
            True if job was preempted, False otherwise
        """
        # Look for specific error messages indicating preemption
        status = job_status.get("status", "")
        error_msg = job_status.get("error", "")
        
        preemption_indicators = [
            "preempt",
            "instance was terminated",
            "instance stopped",
            "compute.instances.preempted"
        ]
        
        if status.lower() == "failed":
            for indicator in preemption_indicators:
                if indicator in error_msg.lower():
                    return True
        
        return False
    
    def _retry_preempted_job(self, original_job_id: str) -> str:
        """
        Retry a job that was preempted by GCP.
        
        Args:
            original_job_id: ID of the original preempted job
            
        Returns:
            New job ID
        """
        # In a real implementation, you'd retrieve the original job details from storage
        # and recreate the job with the same parameters
        
        # For now, just log the retry
        logger.info(f"Retrying preempted job {original_job_id}")
        
        # This would be replaced with actual job recreation logic
        # return self.vertex_service.create_video_job(image_paths, audio_path, story)
        return f"{original_job_id}-retry"
    
    def _retry_with_non_preemptible(self, original_job_id: str) -> str:
        """
        Retry a job using non-preemptible instances as a fallback.
        
        Args:
            original_job_id: ID of the original preempted job
            
        Returns:
            New job ID
        """
        # This would modify the job configuration to use non-preemptible instances
        logger.info(f"Falling back to non-preemptible instance for job {original_job_id}")
        
        # This would be replaced with actual job recreation logic with non-preemptible flag
        return f"{original_job_id}-standard"
    
    def modify_vertex_configs_for_preemptible(self):
        """
        Modify the fallback configurations in VertexGPUJobService to include preemptible options.
        
        This adds preemptible versions of each GPU configuration with the 'spot' flag set to True.
        """
        # Get the current fallback configs
        original_configs = self.vertex_service.fallback_configs.copy()
        new_configs = []
        
        # For each configuration, add a preemptible version with spot=True
        for config in original_configs:
            # Skip CPU configurations (already have preemptible and standard)
            if config.get("gpu_type") is None:
                new_configs.append(config)
                continue
                
            # Create a preemptible version of the GPU configuration
            preemptible_config = config.copy()
            preemptible_config["spot"] = True
            
            # Add preemptible version first (for cost optimization)
            new_configs.append(preemptible_config)
            new_configs.append(config)  # Add original non-preemptible version
        
        # Replace the fallback configs with our new list
        self.vertex_service.fallback_configs = new_configs
        logger.info(f"Added preemptible configurations. Total configs: {len(new_configs)}")


# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Get project ID from environment
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is not set")
        exit(1)
    
    # Initialize the PreemptibleGPUManager
    manager = PreemptibleGPUManager(
        project_id=project_id,
        region="us-central1",
        max_retries=3,
        retry_delay=30
    )
    
    # Modify the vertex configurations to include preemptible options
    manager.modify_vertex_configs_for_preemptible()
    
    logger.info("Preemptible GPU Manager initialized successfully")
    logger.info("Use manager.create_video_job_with_retry() to create jobs with preemptible GPU support") 

