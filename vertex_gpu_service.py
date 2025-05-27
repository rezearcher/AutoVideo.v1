"""
Vertex AI GPU Job Service
Handles triggering and monitoring GPU video processing jobs
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, Optional
from google.cloud import aiplatform
from google.cloud import storage
import time

logger = logging.getLogger(__name__)

class VertexGPUJobService:
    def __init__(self, project_id: str, region: str = "us-central1", bucket_name: str = None):
        self.project_id = project_id
        self.region = region
        self.bucket_name = bucket_name or f"{project_id}-video-jobs"
        
        # Initialize Vertex AI
        aiplatform.init(project=project_id, location=region)
        
        # Initialize Storage client
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)
        
        # GPU job configuration
        self.container_image = f"gcr.io/{project_id}/av-gpu-job"
        self.machine_type = "n1-standard-4"
        self.accelerator_type = "NVIDIA_TESLA_T4"
        self.accelerator_count = 1
    
    def create_job_config(self, job_id: str, job_data: Dict[str, Any]) -> str:
        """Upload job configuration to GCS"""
        try:
            blob_name = f"jobs/{job_id}/config.json"
            blob = self.bucket.blob(blob_name)
            
            blob.upload_from_string(
                json.dumps(job_data, indent=2),
                content_type='application/json'
            )
            
            logger.info(f"Uploaded job config: gs://{self.bucket_name}/{blob_name}")
            return f"gs://{self.bucket_name}/{blob_name}"
            
        except Exception as e:
            logger.error(f"Failed to upload job config: {e}")
            raise
    
    def submit_gpu_job(self, script: str, voice_settings: Dict[str, Any], 
                      video_settings: Dict[str, Any]) -> str:
        """Submit a new GPU video processing job"""
        try:
            # Generate unique job ID
            job_id = f"video-job-{uuid.uuid4().hex[:8]}"
            
            # Prepare job data
            job_data = {
                "job_id": job_id,
                "script": script,
                "voice_settings": voice_settings,
                "video_settings": video_settings,
                "created_at": time.time()
            }
            
            # Upload job configuration to GCS
            self.create_job_config(job_id, job_data)
            
            # Create Vertex AI Custom Job
            job_spec = {
                "display_name": f"av-gpu-job-{job_id}",
                "job_spec": {
                    "worker_pool_specs": [
                        {
                            "machine_spec": {
                                "machine_type": self.machine_type,
                                "accelerator_type": self.accelerator_type,
                                "accelerator_count": self.accelerator_count,
                            },
                            "replica_count": 1,
                            "container_spec": {
                                "image_uri": self.container_image,
                                "args": [
                                    "--job-id", job_id,
                                    "--project-id", self.project_id,
                                    "--bucket-name", self.bucket_name
                                ],
                                "env": [
                                    {"name": "GOOGLE_CLOUD_PROJECT", "value": self.project_id}
                                ]
                            },
                        }
                    ]
                }
            }
            
            # Submit the job
            job = aiplatform.CustomJob.from_local_script(
                display_name=f"av-gpu-job-{job_id}",
                script_path="gpu_worker.py",
                container_uri=self.container_image,
                machine_type=self.machine_type,
                accelerator_type=self.accelerator_type,
                accelerator_count=self.accelerator_count,
                args=[
                    "--job-id", job_id,
                    "--project-id", self.project_id,
                    "--bucket-name", self.bucket_name
                ]
            )
            
            # Start the job asynchronously
            job.run(sync=False)
            
            logger.info(f"Submitted GPU job: {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to submit GPU job: {e}")
            raise
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a GPU job"""
        try:
            # Check for status file in GCS
            status_blob_name = f"jobs/{job_id}/status.json"
            status_blob = self.bucket.blob(status_blob_name)
            
            if status_blob.exists():
                status_data = json.loads(status_blob.download_as_text())
                return status_data
            else:
                # Job is still running or hasn't started
                return {
                    "status": "running",
                    "job_id": job_id,
                    "message": "Job is in progress"
                }
                
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return {
                "status": "error",
                "job_id": job_id,
                "error": str(e)
            }
    
    def get_job_result(self, job_id: str) -> Optional[str]:
        """Get the video URL if job is completed"""
        try:
            status = self.get_job_status(job_id)
            
            if status.get("status") == "completed":
                return status.get("video_url")
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to get job result: {e}")
            return None
    
    def wait_for_job_completion(self, job_id: str, timeout: int = 600) -> Dict[str, Any]:
        """Wait for job completion with timeout"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_job_status(job_id)
            
            if status.get("status") in ["completed", "failed", "error"]:
                return status
            
            # Wait before checking again
            time.sleep(10)
        
        # Timeout reached
        return {
            "status": "timeout",
            "job_id": job_id,
            "message": f"Job did not complete within {timeout} seconds"
        } 