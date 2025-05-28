"""
Vertex AI GPU Job Service
Handles triggering and monitoring GPU video processing jobs
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, Optional, List
from google.cloud import aiplatform
from google.cloud import storage
import time
from google.cloud.aiplatform import gapic
import google.auth
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

class VertexGPUJobService:
    def __init__(self, project_id: str, region: str = "us-central1", bucket_name: str = None):
        try:
            logger.info("🔧 Initializing VertexGPUJobService...")
            
            self.project_id = project_id
            self.region = region
            # Use environment variable for bucket name to avoid hardcoding sensitive info
            self.bucket_name = bucket_name or os.getenv('VERTEX_BUCKET_NAME', f"{project_id}-video-jobs")
            
            logger.info(f"📋 Project: {self.project_id}, Region: {self.region}, Bucket: {self.bucket_name}")
            
            # Initialize Vertex AI with proper regional endpoint
            logger.info("🚀 Initializing Vertex AI with regional endpoint...")
            aiplatform.init(
                project=project_id, 
                location=region,
                staging_bucket=f"gs://{self.bucket_name}"
            )
            
            # Initialize the GAPIC client with explicit regional endpoint and timeout
            logger.info(f"🌐 Initializing JobServiceClient for region {region}...")
            self.job_client = gapic.JobServiceClient(
                client_options={"api_endpoint": f"{region}-aiplatform.googleapis.com"}
            )
            logger.info("✅ Vertex AI and JobServiceClient initialized successfully")
            
            # Initialize Storage client with timeout
            logger.info("💾 Initializing GCS client...")
            self.storage_client = storage.Client(project=project_id)
            self.bucket = self.storage_client.bucket(self.bucket_name)
            logger.info("✅ GCS client initialized successfully")
            
            # GPU job configuration - using preemptible T4 for cost savings and higher quota
            self.container_image = f"gcr.io/{project_id}/av-gpu-job"
            self.machine_type = "n1-standard-4"
            # Try preemptible T4 first for higher quota availability and 80% cost savings
            self.accelerator_type = "NVIDIA_TESLA_T4"
            self.accelerator_count = 1
            self.use_preemptible = True  # Enable preemptible instances for cost savings
            
            logger.info(f"🎯 GPU config: {self.container_image}, {self.machine_type}, {self.accelerator_type} (preemptible: {self.use_preemptible})")
            logger.info("✅ VertexGPUJobService initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize VertexGPUJobService: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            logger.error(f"❌ Error details: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            raise
    
    def upload_assets_to_gcs(self, job_id: str, image_paths: List[str], audio_path: str) -> Dict[str, Any]:
        """Upload images and audio to GCS with retry logic"""
        try:
            logger.info(f"Uploading assets to GCS for job {job_id}")
            
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
                    logger.info(f"Uploaded image {i}: {image_url}")
                else:
                    logger.warning(f"Image file not found: {image_path}")
            
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
                logger.info(f"Uploaded audio: {asset_urls['audio_url']}")
            else:
                logger.warning(f"Audio file not found: {audio_path}")
            
            return asset_urls
            
        except Exception as e:
            logger.error(f"Failed to upload assets to GCS: {e}")
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
            
            logger.info(f"Uploaded job config: gs://{self.bucket_name}/{blob_name}")
            return f"gs://{self.bucket_name}/{blob_name}"
            
        except Exception as e:
            logger.error(f"Failed to upload job config: {e}")
            raise
    
    def create_job_spec(self, job_id: str) -> Dict[str, Any]:
        """Create job specification with preemptible GPU settings for cost savings and higher quota"""
        return {
            "display_name": f"av-gpu-job-{job_id}",
            "job_spec": {
                "worker_pool_specs": [
                    {
                        "machine_spec": {
                            "machine_type": self.machine_type,
                            "accelerator_type": self.accelerator_type,
                            "accelerator_count": self.accelerator_count,
                        },
                        "spot": self.use_preemptible,  # Enable preemptible/spot instances
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
                # Enable preemptible instances for 80% cost savings and higher quota availability
                "scheduling": {
                    "restart_job_on_worker_restart": True
                }
            }
        }
    
    def submit_gpu_job(self, script: str, voice_settings: Dict[str, Any], 
                      video_settings: Dict[str, Any], image_paths: List[str] = None, 
                      audio_path: str = None) -> str:
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
            
            # Upload assets if provided
            if image_paths and audio_path:
                asset_urls = self.upload_assets_to_gcs(job_id, image_paths, audio_path)
                job_data.update(asset_urls)
            
            # Upload job configuration to GCS
            self.create_job_config(job_id, job_data)
            
            # Submit the job
            logger.info("🚀 Creating Vertex AI CustomJob...")
            try:
                # Create job specification using GAPIC format
                logger.info("📋 Building job specification...")
                job_spec = self.create_job_spec(job_id)
                logger.info("✅ Job specification built")
                
                # Submit job with timeout using GAPIC client
                logger.info("🎬 Submitting job to Vertex AI with 60s timeout...")
                try:
                    response = self.job_client.create_custom_job(
                        parent=f"projects/{self.project_id}/locations/{self.region}",
                        custom_job=job_spec,
                        timeout=60  # 60 second timeout for job submission
                    )
                    logger.info(f"✅ Job submitted successfully: {response.name}")
                    logger.info(f"🎯 Job resource name: {response.name}")
                    
                    # Extract job ID from response
                    vertex_job_id = response.name.split('/')[-1]
                    logger.info(f"🆔 Vertex AI job ID: {vertex_job_id}")
                    
                    return job_id
                    
                except Exception as submission_error:
                    logger.error(f"❌ Job submission failed: {submission_error}")
                    logger.error(f"❌ Submission error type: {type(submission_error).__name__}")
                    logger.error(f"❌ Submission error details: {str(submission_error)}")
                    
                    # Check if it's a timeout or network issue
                    if "timeout" in str(submission_error).lower() or "deadline" in str(submission_error).lower():
                        logger.error("🕐 Job submission timed out - likely network connectivity issue")
                    elif "permission" in str(submission_error).lower() or "auth" in str(submission_error).lower():
                        logger.error("🔐 Authentication/permission issue detected")
                    elif "quota" in str(submission_error).lower():
                        logger.error("📊 Quota limit reached")
                    
                    raise submission_error
                
            except Exception as vertex_error:
                logger.error(f"❌ Vertex AI job creation failed: {vertex_error}")
                logger.error(f"❌ Error type: {type(vertex_error).__name__}")
                logger.error(f"❌ Error details: {str(vertex_error)}")
                import traceback
                logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                raise
            
        except Exception as e:
            logger.error(f"Failed to submit GPU job: {e}")
            raise
    
    def create_video_job(self, image_paths: List[str], audio_path: str, story: str) -> str:
        """Create a video job from images, audio, and story"""
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
            
            # Submit the job
            logger.info("🚀 Creating Vertex AI CustomJob...")
            try:
                # Create job specification using GAPIC format
                logger.info("📋 Building job specification...")
                job_spec = self.create_job_spec(job_id)
                logger.info("✅ Job specification built")
                
                # Submit job with timeout using GAPIC client
                logger.info("🎬 Submitting job to Vertex AI with 60s timeout...")
                try:
                    response = self.job_client.create_custom_job(
                        parent=f"projects/{self.project_id}/locations/{self.region}",
                        custom_job=job_spec,
                        timeout=60  # 60 second timeout for job submission
                    )
                    logger.info(f"✅ Job submitted successfully: {response.name}")
                    logger.info(f"🎯 Job resource name: {response.name}")
                    
                    # Extract job ID from response
                    vertex_job_id = response.name.split('/')[-1]
                    logger.info(f"🆔 Vertex AI job ID: {vertex_job_id}")
                    
                    return job_id
                    
                except Exception as submission_error:
                    logger.error(f"❌ Job submission failed: {submission_error}")
                    logger.error(f"❌ Submission error type: {type(submission_error).__name__}")
                    logger.error(f"❌ Submission error details: {str(submission_error)}")
                    
                    # Check if it's a timeout or network issue
                    if "timeout" in str(submission_error).lower() or "deadline" in str(submission_error).lower():
                        logger.error("🕐 Job submission timed out - likely network connectivity issue")
                    elif "permission" in str(submission_error).lower() or "auth" in str(submission_error).lower():
                        logger.error("🔐 Authentication/permission issue detected")
                    elif "quota" in str(submission_error).lower():
                        logger.error("📊 Quota limit reached")
                    
                    raise submission_error
                
            except Exception as vertex_error:
                logger.error(f"❌ Vertex AI job creation failed: {vertex_error}")
                logger.error(f"❌ Error type: {type(vertex_error).__name__}")
                logger.error(f"❌ Error details: {str(vertex_error)}")
                import traceback
                logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                raise
            
        except Exception as e:
            logger.error(f"❌ Failed to create video job: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            logger.error(f"❌ Error details: {str(e)}")
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
    
    def download_video_result(self, job_id: str, local_path: str) -> bool:
        """Download the completed video from GCS to local path"""
        try:
            video_url = self.get_job_result(job_id)
            if not video_url:
                logger.error("No video result available")
                return False
            
            # Extract blob name from GCS URL
            blob_name = video_url.replace(f"gs://{self.bucket_name}/", "")
            blob = self.bucket.blob(blob_name)
            
            # Download to local path
            blob.download_to_filename(local_path)
            logger.info(f"Downloaded video to: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download video result: {e}")
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