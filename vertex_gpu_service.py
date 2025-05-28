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

def get_gpu_quota(project: str, region: str, gpu_type: str = "T4") -> Optional[Dict[str, int]]:
    """Get GPU quota information for a specific region and type"""
    try:
        from google.auth import default
        from googleapiclient.discovery import build
        
        # Map GPU types to Compute Engine quota metric names
        metric_map = {
            "T4": "NVIDIA_T4_GPUS",
            "L4": "NVIDIA_L4_GPUS"
        }
        
        target_metric = metric_map.get(gpu_type)
        if not target_metric:
            return None
            
        creds, _ = default()
        compute = build("compute", "v1", credentials=creds, cache_discovery=False)
        
        region_info = compute.regions().get(project=project, region=region).execute()
        
        for quota in region_info.get('quotas', []):
            if quota.get('metric') == target_metric:
                usage = quota.get('usage', 0)
                limit = quota.get('limit', 0)
                available = limit - usage
                return {
                    'usage': usage,
                    'limit': limit,
                    'available': available
                }
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get quota for {gpu_type} in {region}: {e}")
        return None

class VertexGPUJobService:
    def __init__(self, project_id: str, region: str = "us-central1", bucket_name: str = None):
        """Initialize the Vertex AI GPU Job Service with intelligent fallback"""
        self.project_id = project_id
        self.primary_region = region
        self.bucket_name = bucket_name or f"{project_id}-vertex-staging"
        
        # Define fallback configurations in priority order
        self.fallback_configs = [
            # Primary: L4 in us-central1 (L4 requires g2-standard-4)
            {"region": "us-central1", "gpu_type": "L4", "gpu_count": 1, "machine_type": "g2-standard-4"},
            # Fallback 1: T4 in us-central1 (T4 works with n1-standard-4)
            {"region": "us-central1", "gpu_type": "T4", "gpu_count": 1, "machine_type": "n1-standard-4"},
            # Fallback 2: L4 in us-west1
            {"region": "us-west1", "gpu_type": "L4", "gpu_count": 1, "machine_type": "g2-standard-4"},
            # Fallback 3: T4 in us-west1
            {"region": "us-west1", "gpu_type": "T4", "gpu_count": 1, "machine_type": "n1-standard-4"},
            # Fallback 4: L4 in us-east1
            {"region": "us-east1", "gpu_type": "L4", "gpu_count": 1, "machine_type": "g2-standard-4"},
            # Fallback 5: T4 in us-east1
            {"region": "us-east1", "gpu_type": "T4", "gpu_count": 1, "machine_type": "n1-standard-4"},
            # Final fallback: CPU only
            {"region": "us-central1", "gpu_type": None, "gpu_count": 0, "machine_type": "n1-standard-8"}
        ]
        
        # Initialize with primary region
        staging_bucket = f"gs://{self.bucket_name}"
        initialize_vertex_ai(project_id, region, staging_bucket)
        
        # Initialize Storage client for asset uploads
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)
        
        logger.info(f"🔧 VertexGPUJobService initialized with project: {project_id}")
        logger.info(f"📍 Primary region: {region}, staging bucket: {staging_bucket}")
        logger.info(f"🔄 Fallback configs available: {len(self.fallback_configs)}")

    def get_best_available_config(self) -> Dict[str, Any]:
        """Find the best available configuration based on quota availability"""
        logger.info("🔍 Checking GPU quota across regions...")
        
        for i, config in enumerate(self.fallback_configs):
            region = config["region"]
            gpu_type = config["gpu_type"]
            
            if gpu_type is None:  # CPU-only fallback
                logger.info(f"✅ Fallback {i+1}: CPU-only in {region} (always available)")
                return config
                
            # Check quota for this configuration
            quota_info = get_gpu_quota(self.project_id, region, gpu_type)
            
            if quota_info and quota_info.get('available', 0) > 0:
                logger.info(f"✅ Fallback {i+1}: {gpu_type} available in {region} (quota: {quota_info})")
                return config
            else:
                quota_msg = f"quota: {quota_info}" if quota_info else "quota check failed"
                logger.warning(f"❌ Fallback {i+1}: {gpu_type} unavailable in {region} ({quota_msg})")
        
        # Should never reach here due to CPU fallback, but just in case
        logger.error("🚨 All fallback configurations exhausted!")
        return self.fallback_configs[-1]  # Return CPU fallback

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
    
    def create_gpu_job_with_fallback(self, job_id: str, config: Dict[str, Any]) -> str:
        """Create GPU job with intelligent fallback across regions and GPU types"""
        logger.info(f"🚀 Creating GPU job {job_id} with intelligent fallback...")
        
        # Find the best available configuration
        best_config = self.get_best_available_config()
        logger.info(f"🎯 Selected configuration: {best_config}")
        
        # If the region differs from current, reinitialize Vertex AI
        current_region = best_config["region"]
        if current_region != self.primary_region:
            logger.info(f"🔄 Switching from {self.primary_region} to {current_region}")
            staging_bucket = f"gs://{self.bucket_name}"
            initialize_vertex_ai(self.project_id, current_region, staging_bucket)
        
        # Upload job configuration
        try:
            job_config_url = self.create_job_config(job_id, config)
            logger.info(f"✅ Job config uploaded: {job_config_url}")
        except Exception as e:
            logger.error(f"❌ Failed to upload job config: {e}")
            raise
        
        # Submit the job with the selected configuration
        return self._submit_job_with_config(job_id, best_config, job_config_url)
    
    def _submit_job_with_config(self, job_id: str, config: Dict[str, Any], job_config_url: str) -> str:
        """Submit job using the specified configuration"""
        display_name = f"av-video-render-{job_id}"
        region = config["region"]
        gpu_type = config["gpu_type"]
        gpu_count = config["gpu_count"]
        machine_type = config["machine_type"]
        
        # Create job labels
        job_labels = {
            "pipeline": "autovideo",
            "phase": "gpu",
            "service": "av-app",
            "job_id": job_id,
            "region": region.replace("-", "_"),
            "environment": os.getenv("ENVIRONMENT", "production")
        }
        
        if gpu_type:
            job_labels["gpu_type"] = gpu_type.lower()
            job_labels["gpu_count"] = str(gpu_count)
        else:
            job_labels["compute_type"] = "cpu"
        
        try:
            logger.info(f"🚀 Submitting job to {region} with {gpu_type or 'CPU'}")
            
            # Prepare worker pool spec
            worker_pool_spec = {
                "machine_spec": {
                    "machine_type": machine_type
                },
                "replica_count": 1,
                "container_spec": {
                    "image_uri": f"gcr.io/{self.project_id}/av-gpu-job",
                    "command": [
                        "python", "/app/gpu_worker.py",
                        "--job-id", job_id,
                        "--project-id", self.project_id,
                        "--bucket-name", self.bucket_name,
                        "--config-url", job_config_url
                    ],
                    "env": [
                        {"name": "GOOGLE_CLOUD_PROJECT", "value": self.project_id},
                        {"name": "VERTEX_AI_REGION", "value": region}
                    ]
                }
            }
            
            # Add GPU configuration if specified
            if gpu_type and gpu_count > 0:
                # Map our friendly GPU names to Vertex AI types
                gpu_type_map = {
                    "T4": "NVIDIA_TESLA_T4",
                    "L4": "NVIDIA_L4"
                }
                
                worker_pool_spec["machine_spec"]["accelerator_type"] = gpu_type_map[gpu_type]
                worker_pool_spec["machine_spec"]["accelerator_count"] = gpu_count
                logger.info(f"🎮 Using {gpu_count}x {gpu_type_map[gpu_type]} on {machine_type}")
            else:
                logger.info(f"🖥️ Using CPU-only: {machine_type}")
            
            # Create and submit the CustomJob
            job = aiplatform.CustomJob(
                display_name=display_name,
                project=self.project_id,
                location=region,
                worker_pool_specs=[worker_pool_spec],
                labels=job_labels
            )
            
            job.submit()
            
            logger.info(f"✅ Job submitted successfully: {job.resource_name}")
            logger.info(f"🎯 Resource name: {job.resource_name}")
            logger.info(f"🏷️ Labels: {job_labels}")
            
            return job_id
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"❌ Job submission failed: {error_str}")
            
            # Check if this is a quota error and we should try next fallback
            if "quota" in error_str.lower() or "resource exhausted" in error_str.lower():
                logger.warning(f"📊 Quota exhausted for {gpu_type or 'CPU'} in {region}")
                # Remove this config from available options and try next
                if config in self.fallback_configs:
                    self.fallback_configs.remove(config)
                    if self.fallback_configs:
                        logger.info("🔄 Trying next fallback configuration...")
                        return self.create_gpu_job_with_fallback(job_id, self._get_job_config_from_url(job_config_url))
            
            raise
    
    def _get_job_config_from_url(self, config_url: str) -> Dict[str, Any]:
        """Retrieve job config from GCS URL (helper for retries)"""
        try:
            # Extract blob name from URL
            blob_name = config_url.replace(f"gs://{self.bucket_name}/", "")
            blob = self.bucket.blob(blob_name)
            config_json = blob.download_as_text()
            return json.loads(config_json)
        except Exception as e:
            logger.error(f"❌ Failed to retrieve job config: {e}")
            return {}

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
            return self.create_gpu_job_with_fallback(job_id, job_data)
            
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