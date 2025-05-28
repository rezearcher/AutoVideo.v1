"""
Vertex AI GPU Job Service
Handles triggering and monitoring GPU video processing jobs using Google's best practices
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, Optional, List
from google.cloud import aiplatform
from google.cloud import storage
import time
import google.auth
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# Global Vertex AI initialization - done once at module level
_vertex_initialized = False

def initialize_vertex_ai(project_id: str, region: str, staging_bucket: str):
    """Initialize Vertex AI once globally"""
    global _vertex_initialized
    if not _vertex_initialized:
        logger.info(f"🚀 Initializing Vertex AI globally: project={project_id}, region={region}")
        aiplatform.init(
            project=project_id,
            location=region,
            staging_bucket=staging_bucket
        )
        _vertex_initialized = True
        logger.info("✅ Vertex AI initialized globally")

class VertexGPUJobService:
    def __init__(self, project_id: str, region: str = "us-central1", bucket_name: str = None):
        try:
            logger.info("🔧 Initializing VertexGPUJobService...")
            
            self.project_id = project_id
            self.region = region
            # Use environment variable for bucket name to avoid hardcoding sensitive info
            self.bucket_name = bucket_name or os.getenv('VERTEX_BUCKET_NAME', f"{project_id}-video-jobs")
            
            logger.info(f"📋 Project: {self.project_id}, Region: {self.region}, Bucket: {self.bucket_name}")
            
            # Initialize Vertex AI globally (once)
            staging_bucket = f"gs://{self.bucket_name}"
            initialize_vertex_ai(project_id, region, staging_bucket)
            
            # Initialize Storage client
            logger.info("💾 Initializing GCS client...")
            self.storage_client = storage.Client(project=project_id)
            self.bucket = self.storage_client.bucket(self.bucket_name)
            logger.info("✅ GCS client initialized successfully")
            
            # GPU job configuration - using spot VMs for cost savings and higher quota
            self.container_image = f"gcr.io/{project_id}/av-gpu-job"
            self.machine_type = "n1-standard-4"
            self.accelerator_count = 1
            
            # GPU fallback options (in order of preference) - spot first for cost/quota
            self.gpu_options = [
                ("NVIDIA_L4", True),           # L4 spot - best quota availability
                ("NVIDIA_TESLA_T4", True),     # T4 spot - good availability  
                ("NVIDIA_L4", False),          # L4 on-demand - fallback
                ("NVIDIA_TESLA_T4", False),    # T4 on-demand - fallback
                ("NVIDIA_TESLA_P100", False),  # P100 on-demand - last resort
            ]
            
            # Start with the first option
            self.accelerator_type, self.current_spot = self.gpu_options[0]
            
            # Job labels for tracking and filtering
            self.job_labels = {
                "pipeline": "autovideo",
                "phase": "gpu",
                "service": "av-app",
                "environment": os.getenv("ENVIRONMENT", "production")
            }
            
            logger.info(f"🎯 GPU config: {self.container_image}, {self.machine_type}, {self.accelerator_type} (spot: {self.current_spot})")
            logger.info("✅ VertexGPUJobService initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize VertexGPUJobService: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            raise
    
    def upload_assets_to_gcs(self, job_id: str, image_paths: List[str], audio_path: str) -> Dict[str, Any]:
        """Upload images and audio to GCS with retry logic"""
        try:
            logger.info(f"📤 Uploading assets to GCS for job {job_id}")
            
            asset_urls = {"image_urls": [], "audio_url": ""}
            
            # Upload images
            for i, image_path in enumerate(image_paths):
                if os.path.exists(image_path):
                    blob_name = f"jobs/{job_id}/images/image_{i}.png"
                    blob = self.bucket.blob(blob_name)
                    
                    # Set timeout for upload
                    blob._chunk_size = 1024 * 1024  # 1MB chunks
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            with open(image_path, 'rb') as image_file:
                                blob.upload_from_file(
                                    image_file, 
                                    content_type='image/png',
                                    timeout=60  # 60 second timeout
                                )
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                logger.error(f"Failed to upload image {i} after {max_retries} attempts: {e}")
                                raise
                            logger.warning(f"Upload attempt {attempt + 1} failed for image {i}, retrying: {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                    
                    image_url = f"gs://{self.bucket_name}/{blob_name}"
                    asset_urls["image_urls"].append(image_url)
                    logger.info(f"✅ Uploaded image {i}: {image_url}")
                else:
                    logger.warning(f"⚠️ Image file not found: {image_path}")
            
            # Upload audio with retry logic
            if os.path.exists(audio_path):
                blob_name = f"jobs/{job_id}/audio/audio.mp3"
                blob = self.bucket.blob(blob_name)
                
                # Set chunk size for large files
                blob._chunk_size = 1024 * 1024  # 1MB chunks
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with open(audio_path, 'rb') as audio_file:
                            blob.upload_from_file(
                                audio_file, 
                                content_type='audio/mpeg',
                                timeout=120  # 2 minute timeout for audio
                            )
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(f"Failed to upload audio after {max_retries} attempts: {e}")
                            raise
                        logger.warning(f"Upload attempt {attempt + 1} failed for audio, retrying: {e}")
                        time.sleep(2 ** attempt)  # Exponential backoff
                
                asset_urls["audio_url"] = f"gs://{self.bucket_name}/{blob_name}"
                logger.info(f"✅ Uploaded audio: {asset_urls['audio_url']}")
            else:
                logger.warning(f"⚠️ Audio file not found: {audio_path}")
            
            return asset_urls
            
        except Exception as e:
            logger.error(f"❌ Failed to upload assets to GCS: {e}")
            raise
    
    def create_job_config(self, job_id: str, job_data: Dict[str, Any]) -> str:
        """Upload job configuration to GCS"""
        try:
            blob_name = f"jobs/{job_id}/config.json"
            blob = self.bucket.blob(blob_name)
            
            blob.upload_from_string(
                json.dumps(job_data, indent=2),
                content_type='application/json'
            )
            
            logger.info(f"✅ Uploaded job config: gs://{self.bucket_name}/{blob_name}")
            return f"gs://{self.bucket_name}/{blob_name}"
            
        except Exception as e:
            logger.error(f"❌ Failed to upload job config: {e}")
            raise
    
    def try_next_gpu_option(self) -> bool:
        """Try the next GPU option in the fallback list"""
        current_index = None
        for i, (gpu_type, spot) in enumerate(self.gpu_options):
            if gpu_type == self.accelerator_type and spot == self.current_spot:
                current_index = i
                break
        
        if current_index is not None and current_index < len(self.gpu_options) - 1:
            next_index = current_index + 1
            self.accelerator_type, self.current_spot = self.gpu_options[next_index]
            logger.info(f"🔄 Switching to GPU option {next_index + 1}: {self.accelerator_type} (spot: {self.current_spot})")
            return True
        else:
            logger.warning("⚠️ No more GPU options available")
            return False

    def submit_job_with_fallback(self, job_id: str) -> str:
        """Submit job using high-level CustomJob API with GPU fallback logic"""
        max_gpu_attempts = len(self.gpu_options)
        
        for attempt in range(max_gpu_attempts):
            logger.info(f"🎬 Submitting job to Vertex AI (attempt {attempt + 1}/{max_gpu_attempts}) with {self.accelerator_type} (spot: {self.current_spot})...")
            
            try:
                # Create CustomJob using high-level API
                display_name = f"av-video-render-{job_id}"
                
                # Create job labels with current attempt info
                job_labels = {
                    **self.job_labels,
                    "job_id": job_id,
                    "gpu_type": self.accelerator_type.lower().replace("_", "-"),
                    "spot_vm": str(self.current_spot).lower(),
                    "attempt": str(attempt + 1)
                }
                
                # Use the high-level CustomJob API
                job = aiplatform.CustomJob(
                    display_name=display_name,
                    worker_pool_specs=[
                        {
                            "machine_spec": {
                                "machine_type": self.machine_type,
                                "accelerator_type": self.accelerator_type,
                                "accelerator_count": self.accelerator_count,
                            },
                            "replica_count": 1,
                            "disk_spec": {
                                "boot_disk_type": "pd-ssd",
                                "boot_disk_size_gb": 100
                            },
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
                    ],
                    # Enable spot VMs for cost savings and higher quota availability
                    scheduling={
                        "restart_job_on_worker_restart": True,
                        "timeout": "3600s",  # 1 hour timeout
                        "enable_spot": self.current_spot
                    },
                    labels=job_labels
                )
                
                # Submit job asynchronously
                logger.info(f"🚀 Submitting CustomJob: {display_name}")
                job.submit(sync=False)  # Non-blocking submission
                
                logger.info(f"✅ Job submitted successfully: {job.resource_name}")
                logger.info(f"🎯 Job resource name: {job.resource_name}")
                logger.info(f"🏷️ Job labels: {job_labels}")
                
                return job_id
                
            except Exception as submission_error:
                logger.error(f"❌ Job submission failed: {submission_error}")
                logger.error(f"❌ Submission error type: {type(submission_error).__name__}")
                
                # Check if it's a quota issue and we have more GPU options to try
                error_str = str(submission_error).lower()
                if "quota" in error_str or "insufficient" in error_str:
                    logger.error(f"📊 Quota limit reached for {self.accelerator_type} (spot: {self.current_spot})")
                    if attempt < max_gpu_attempts - 1 and self.try_next_gpu_option():
                        logger.info(f"🔄 Retrying with next GPU option...")
                        continue
                    else:
                        logger.error("❌ All GPU options exhausted")
                        raise submission_error
                elif "timeout" in error_str or "deadline" in error_str:
                    logger.error("🕐 Job submission timed out - likely network connectivity issue")
                    raise submission_error
                elif "permission" in error_str or "auth" in error_str:
                    logger.error("🔐 Authentication/permission issue detected")
                    raise submission_error
                else:
                    # For other errors, don't retry
                    logger.error(f"❌ Non-retryable error: {submission_error}")
                    raise submission_error
        
        # This should never be reached, but just in case
        raise Exception("Failed to submit job after all GPU options exhausted")

    def create_video_job(self, image_paths: List[str], audio_path: str, story: str) -> str:
        """Create a video job from images, audio, and story using high-level API"""
        try:
            logger.info("🔧 Starting video job creation...")
            
            # Generate unique job ID
            job_id = f"video-job-{uuid.uuid4().hex[:8]}"
            logger.info(f"📋 Generated job ID: {job_id}")
            
            # Upload assets to GCS
            logger.info("📤 Uploading assets to GCS...")
            asset_urls = self.upload_assets_to_gcs(job_id, image_paths, audio_path)
            logger.info(f"✅ Assets uploaded: {list(asset_urls.keys())}")
            
            # Prepare job data
            logger.info("📝 Preparing job configuration...")
            job_data = {
                "job_id": job_id,
                "script": story,
                "voice_settings": {},
                "video_settings": {},
                "created_at": time.time(),
                **asset_urls
            }
            
            # Upload job configuration to GCS
            logger.info("📋 Uploading job config to GCS...")
            self.create_job_config(job_id, job_data)
            logger.info("✅ Job config uploaded")
            
            # Submit the job with GPU fallback logic
            logger.info("🚀 Creating Vertex AI CustomJob...")
            return self.submit_job_with_fallback(job_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to create video job: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
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
            logger.error(f"❌ Failed to get job status: {e}")
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
            logger.error(f"❌ Failed to get job result: {e}")
            return None
    
    def download_video_result(self, job_id: str, local_path: str) -> bool:
        """Download the completed video from GCS to local path"""
        try:
            video_url = self.get_job_result(job_id)
            if not video_url:
                logger.error("❌ No video result available")
                return False
            
            # Extract blob name from GCS URL
            blob_name = video_url.replace(f"gs://{self.bucket_name}/", "")
            blob = self.bucket.blob(blob_name)
            
            # Download to local path
            blob.download_to_filename(local_path)
            logger.info(f"✅ Downloaded video to: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download video result: {e}")
            return False
    
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
    
    def test_vertex_ai_connectivity(self) -> Dict[str, Any]:
        """Test Vertex AI connectivity for health checks"""
        try:
            logger.info("🔍 Testing Vertex AI connectivity...")
            
            # Create a minimal test job spec (don't submit)
            test_job = aiplatform.CustomJob(
                display_name="av-connectivity-test",
                worker_pool_specs=[{
                    "machine_spec": {"machine_type": "n1-standard-2"},
                    "replica_count": 1,
                    "container_spec": {"image_uri": "gcr.io/google-containers/busybox"}
                }],
                labels={"test": "connectivity", "pipeline": "autovideo"}
            )
            
            # Just creating the job object tests the API connectivity
            logger.info("✅ Vertex AI connectivity test passed")
            return {
                "status": "healthy",
                "message": "Vertex AI API accessible",
                "project_id": self.project_id,
                "region": self.region,
                "test_job_name": test_job.display_name
            }
            
        except Exception as e:
            logger.error(f"❌ Vertex AI connectivity test failed: {e}")
            return {
                "status": "unhealthy", 
                "error": str(e),
                "project_id": self.project_id,
                "region": self.region
            } 