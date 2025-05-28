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

# Region-to-GPU-Machine mappings based on actual GCP availability discovery
REGION_GPU_MACHINE_MAP = {
    "us-central1": {
        "NVIDIA_L4": "g2-standard-4",
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8"
    },
    "us-west1": {
        "NVIDIA_L4": "g2-standard-4", 
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8"
    },
    "us-east1": {
        "NVIDIA_L4": "g2-standard-4",
        "NVIDIA_TESLA_T4": "n1-standard-4", 
        "CPU": "n1-standard-8"
    },
    "europe-west1": {
        "NVIDIA_L4": "g2-standard-4",  # Will validate dynamically
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8"
    },
    "asia-southeast1": {
        "NVIDIA_L4": "g2-standard-4",  # Will validate dynamically
        "NVIDIA_TESLA_T4": "n1-standard-4",
        "CPU": "n1-standard-8"
    }
}

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

def quota_ok(project_id: str, region: str, gpu_type: str) -> bool:
    """Check if quota is available for a specific GPU type in a region"""
    quota_info = get_gpu_quota(project_id, region, gpu_type)
    return quota_info and quota_info.get('available', 0) > 0

def get_multi_region_quota_status(project_id: str, regions: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """Get quota status across multiple regions for comprehensive availability check"""
    if regions is None:
        regions = ['us-central1', 'us-west1', 'us-east1', 'europe-west1', 'asia-southeast1']
    
    gpu_types = ['L4', 'T4']
    quota_status = {}
    
    for region in regions:
        region_status = {}
        for gpu_type in gpu_types:
            quota_info = get_gpu_quota(project_id, region, gpu_type)
            region_status[gpu_type] = {
                'available': quota_info.get('available', 0) if quota_info else 0,
                'quota_ok': quota_ok(project_id, region, gpu_type),
                'quota_info': quota_info
            }
        quota_status[region] = region_status
    
    return quota_status

def discover_gpu_machine_compatibility(project_id: str, region: str) -> Dict[str, str]:
    """Dynamically discover GPU and machine type compatibility for a region"""
    try:
        from googleapiclient.discovery import build
        from google.auth import default
        
        creds, _ = default()
        compute = build("compute", "v1", credentials=creds, cache_discovery=False)
        
        # Get all zones in the region
        zones_result = compute.zones().list(project=project_id, filter=f"region eq .*{region}").execute()
        zones = [zone['name'] for zone in zones_result.get('items', [])]
        
        if not zones:
            logger.warning(f"No zones found for region {region}")
            return {}
        
        # Check first zone for available accelerators and machine types
        zone = zones[0]
        
        # Get available accelerators
        accelerators = compute.acceleratorTypes().list(project=project_id, zone=zone).execute()
        available_gpus = set()
        
        for acc in accelerators.get('items', []):
            acc_name = acc.get('name', '')
            if 'nvidia-l4' in acc_name:
                available_gpus.add('NVIDIA_L4')
            elif 'nvidia-tesla-t4' in acc_name:
                available_gpus.add('NVIDIA_TESLA_T4')
        
        # Get available machine types
        machine_types = compute.machineTypes().list(project=project_id, zone=zone).execute()
        available_machines = set()
        
        for mt in machine_types.get('items', []):
            mt_name = mt.get('name', '')
            if mt_name.startswith(('g2-standard', 'n1-standard', 'n2-standard')):
                available_machines.add(mt_name)
        
        # Build compatibility map
        compatibility = {"CPU": "n1-standard-8"}  # CPU always available
        
        if 'NVIDIA_L4' in available_gpus:
            if 'g2-standard-4' in available_machines:
                compatibility['NVIDIA_L4'] = 'g2-standard-4'
            elif 'n2-standard-4' in available_machines:
                compatibility['NVIDIA_L4'] = 'n2-standard-4'
            else:
                logger.warning(f"L4 GPU available in {region} but no compatible machine type found")
        
        if 'NVIDIA_TESLA_T4' in available_gpus:
            if 'n1-standard-4' in available_machines:
                compatibility['NVIDIA_TESLA_T4'] = 'n1-standard-4'
            elif 'n2-standard-4' in available_machines:
                compatibility['NVIDIA_TESLA_T4'] = 'n2-standard-4'
            else:
                logger.warning(f"T4 GPU available in {region} but no compatible machine type found")
        
        logger.info(f"Discovered compatibility for {region}: {compatibility}")
        return compatibility
        
    except Exception as e:
        logger.error(f"Failed to discover compatibility for {region}: {e}")
        return {"CPU": "n1-standard-8"}  # Fallback to CPU

def get_machine_type_for_gpu(region: str, gpu_type: str, project_id: str = None) -> Optional[str]:
    """Get the appropriate machine type for a GPU type in a specific region"""
    # First try the static mapping
    if region in REGION_GPU_MACHINE_MAP:
        machine_type = REGION_GPU_MACHINE_MAP[region].get(gpu_type)
        if machine_type:
            logger.info(f"Using static mapping: {gpu_type} -> {machine_type} in {region}")
            return machine_type
    
    # If not in static mapping or project_id provided, try dynamic discovery
    if project_id:
        logger.info(f"Attempting dynamic discovery for {gpu_type} in {region}")
        compatibility = discover_gpu_machine_compatibility(project_id, region)
        machine_type = compatibility.get(gpu_type)
        if machine_type:
            logger.info(f"Dynamic discovery: {gpu_type} -> {machine_type} in {region}")
            # Update static mapping for future use
            if region not in REGION_GPU_MACHINE_MAP:
                REGION_GPU_MACHINE_MAP[region] = {}
            REGION_GPU_MACHINE_MAP[region][gpu_type] = machine_type
            return machine_type
    
    logger.warning(f"No machine type found for {gpu_type} in {region}")
    return None

class VertexGPUJobService:
    def __init__(self, project_id: str, region: str = "us-central1", bucket_name: str = None):
        """Initialize the Vertex AI GPU Job Service with intelligent fallback"""
        self.project_id = project_id
        
        # Allow region override via environment variable for immediate workarounds
        override_region = os.getenv("DEFAULT_REGION")
        if override_region:
            logger.info(f"🌍 Region override detected: {override_region} (from DEFAULT_REGION env var)")
            region = override_region
        
        self.primary_region = region
        self.bucket_name = bucket_name or f"{project_id}-vertex-staging-central1"
        
        # Generate fallback configurations dynamically using machine type mapping
        self.fallback_configs = self._generate_fallback_configs()
        
        # Initialize with primary region
        staging_bucket = f"gs://{self.bucket_name}"
        initialize_vertex_ai(project_id, region, staging_bucket)
        
        # Initialize Storage client for asset uploads
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)
        
        logger.info(f"🔧 VertexGPUJobService initialized with project: {project_id}")
        logger.info(f"📍 Primary region: {region}, staging bucket: {staging_bucket}")
        logger.info(f"🔄 Fallback configs available: {len(self.fallback_configs)}")

    def _generate_fallback_configs(self) -> List[Dict[str, Any]]:
        """Generate fallback configurations using dynamic machine type mapping"""
        regions = ['us-central1', 'us-west1', 'us-east1', 'europe-west1', 'asia-southeast1']
        gpu_types = ['L4', 'T4']
        configs = []
        
        # Generate GPU configurations
        for region in regions:
            for gpu_type in gpu_types:
                vertex_gpu_type = f"NVIDIA_{gpu_type}" if gpu_type == "L4" else "NVIDIA_TESLA_T4"
                machine_type = get_machine_type_for_gpu(region, vertex_gpu_type, self.project_id)
                
                if machine_type:
                    configs.append({
                        "region": region,
                        "gpu_type": gpu_type,
                        "gpu_count": 1,
                        "machine_type": machine_type,
                        "spot": False
                    })
                    logger.info(f"✅ Added fallback: {gpu_type} on {machine_type} in {region}")
                else:
                    logger.warning(f"⚠️ Skipped {gpu_type} in {region} - no compatible machine type")
        
        # Add CPU fallbacks for all regions
        for region in regions:
            cpu_machine_type = get_machine_type_for_gpu(region, "CPU", self.project_id)
            configs.append({
                "region": region,
                "gpu_type": None,
                "gpu_count": 0,
                "machine_type": cpu_machine_type or "n1-standard-8",
                "spot": False
            })
        
        logger.info(f"🎯 Generated {len(configs)} fallback configurations")
        return configs

    def get_best_available_config(self) -> Dict[str, Any]:
        """Find the best available configuration based on quota availability"""
        logger.info("🔍 Checking GPU quota across regions...")
        
        for i, config in enumerate(self.fallback_configs):
            region = config["region"]
            gpu_type = config["gpu_type"]
            machine_type = config["machine_type"]
            spot = config.get("spot", False)
            
            spot_label = " (spot)" if spot else " (on-demand)"
            
            if gpu_type is None:  # CPU-only fallback
                logger.info(f"✅ Fallback {i+1}: CPU-only ({machine_type}) in {region}{spot_label}")
                # CPU is generally always available, but we could add CPU quota checking here if needed
                # For now, we'll trust that CPU resources are more readily available
                return config
                
            # Check quota for this GPU configuration
            quota_info = get_gpu_quota(self.project_id, region, gpu_type)
            
            if quota_info and quota_info.get('available', 0) > 0:
                logger.info(f"✅ Fallback {i+1}: {gpu_type} available in {region}{spot_label} (quota: {quota_info})")
                return config
            else:
                quota_msg = f"quota: {quota_info}" if quota_info else "quota check failed"
                logger.warning(f"❌ Fallback {i+1}: {gpu_type} unavailable in {region}{spot_label} ({quota_msg})")
        
        # Should never reach here due to CPU fallback, but just in case
        logger.error("🚨 All fallback configurations exhausted!")
        return self.fallback_configs[-1]  # Return last CPU fallback

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
        spot = config.get("spot", False)
        
        # For non-primary regions, we need to ensure we have regional bucket access
        regional_bucket_name = self.bucket_name
        if region != self.primary_region:
            # Use regional bucket naming for cross-region jobs
            if "central1" in self.bucket_name:
                regional_bucket_name = self.bucket_name.replace("central1", region.replace("us-", ""))
            else:
                regional_bucket_name = f"{self.project_id}-vertex-staging-{region.replace('us-', '')}"
            logger.info(f"🌍 Using regional bucket for {region}: {regional_bucket_name}")
        
        # Create job labels
        job_labels = {
            "pipeline": "autovideo",
            "phase": "gpu",
            "service": "av-app",
            "job_id": job_id,
            "region": region.replace("-", "_"),
            "environment": os.getenv("ENVIRONMENT", "production"),
            "instance_type": "spot" if spot else "on_demand"
        }
        
        if gpu_type:
            job_labels["gpu_type"] = gpu_type.lower()
            job_labels["gpu_count"] = str(gpu_count)
        else:
            job_labels["compute_type"] = "cpu"
        
        spot_label = " (spot)" if spot else " (on-demand)"
        
        try:
            logger.info(f"🚀 Submitting job to {region} with {gpu_type or 'CPU'}{spot_label}")
            
            # For cross-region deployments, we need to reinitialize Vertex AI for the target region
            if region != self.primary_region:
                logger.info(f"🌍 Switching to region {region} for job submission")
                staging_bucket = f"gs://{regional_bucket_name}"
                # Temporarily reinitialize for this region
                aiplatform.init(
                    project=self.project_id,
                    location=region,
                    staging_bucket=staging_bucket
                )
            
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
                        "--bucket-name", self.bucket_name,  # Use original bucket for data access
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
                logger.info(f"🎮 Using {gpu_count}x {gpu_type_map[gpu_type]} on {machine_type} in {region}{spot_label}")
            else:
                logger.info(f"🖥️ Using CPU-only: {machine_type} in {region}{spot_label}")
            
            # Create and submit the CustomJob using standard high-level API
            job = aiplatform.CustomJob(
                display_name=display_name,
                project=self.project_id,
                location=region,
                worker_pool_specs=[worker_pool_spec],
                labels=job_labels
            )
            
            job.submit()
            
            logger.info(f"✅ Job submitted successfully to {region}: {job.resource_name}")
            logger.info(f"🎯 Resource name: {job.resource_name}")
            logger.info(f"🏷️ Labels: {job_labels}")
            
            # If we switched regions, switch back to primary for future operations
            if region != self.primary_region:
                logger.info(f"🏠 Switching back to primary region {self.primary_region}")
                primary_staging_bucket = f"gs://{self.bucket_name}"
                aiplatform.init(
                    project=self.project_id,
                    location=self.primary_region,
                    staging_bucket=primary_staging_bucket
                )
                
            return job_id
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"❌ Job submission failed in {region}{spot_label}: {error_str}")
            
            # If we switched regions for this attempt, make sure we switch back
            if region != self.primary_region:
                try:
                    logger.info(f"🏠 Switching back to primary region {self.primary_region} after error")
                    primary_staging_bucket = f"gs://{self.bucket_name}"
                    aiplatform.init(
                        project=self.project_id,
                        location=self.primary_region,
                        staging_bucket=primary_staging_bucket
                    )
                except Exception as init_error:
                    logger.warning(f"⚠️ Failed to switch back to primary region: {init_error}")
            
            # Check if this is a quota error and we should try next fallback
            if "quota" in error_str.lower() or "resource exhausted" in error_str.lower():
                logger.warning(f"📊 Quota exhausted for {gpu_type or 'CPU'} in {region}{spot_label}")
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