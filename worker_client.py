import os
import logging
import subprocess
import aiohttp
import asyncio
from typing import List, Optional

logger = logging.getLogger(__name__)

class WorkerClient:
    def __init__(self, worker_url: str):
        self.worker_url = worker_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @staticmethod
    def create_worker(project_id: str) -> Optional[str]:
        """Get the existing GPU worker URL."""
        try:
            # Use the existing av-gpu-worker service with the correct URL format
            worker_url = "https://av-gpu-worker-u6sfbxnveq-uc.a.run.app"
            
            # Test if the worker is accessible
            import requests
            try:
                response = requests.get(f"{worker_url}/health", timeout=10)
                if response.status_code == 200:
                    logger.info(f"GPU worker is healthy at {worker_url}")
                    return worker_url
                else:
                    logger.warning(f"GPU worker health check failed with status {response.status_code}")
                    # Still return the URL as it might be temporarily unavailable
                    return worker_url
            except requests.exceptions.RequestException as e:
                logger.warning(f"GPU worker health check failed: {e}")
                # Still return the URL as it might be temporarily unavailable
                return worker_url
                
        except Exception as e:
            logger.error(f"Error getting worker URL: {e}")
            return None

    def process_video(self, image_paths: List[str], output_path: str, audio_path: str, story: str = "") -> bool:
        """Process video using the GPU worker."""
        import requests
        
        try:
            # Prepare job data with the new structure
            job_data = {
                "image_paths": image_paths,
                "audio_path": audio_path,
                "output_path": output_path,
                "story": story,
                "job_id": f"job_{os.path.basename(output_path).replace('.mp4', '')}"
            }
            
            logger.info(f"Sending job to GPU worker: {job_data}")
            
            # Send job to worker
            response = requests.post(f"{self.worker_url}/process", json=job_data, timeout=300)
            if response.status_code != 200:
                logger.error(f"Worker returned status {response.status_code}: {response.text}")
                return False
                
            result = response.json()
            logger.info(f"Worker response: {result}")
            
            # Check if job was accepted for processing
            if result.get("status") == "processing":
                # Wait for completion by checking status file
                return self._wait_for_completion(output_path)
            else:
                logger.error(f"Job not accepted: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return False

    def _wait_for_completion(self, output_path: str, timeout: int = 600) -> bool:
        """Wait for job completion by checking status file"""
        import time
        import json
        
        status_file = f"{output_path}.status"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if os.path.exists(status_file):
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)
                    
                    status = status_data.get("status")
                    if status == "completed":
                        logger.info("Job completed successfully")
                        # Clean up status file
                        try:
                            os.remove(status_file)
                        except:
                            pass
                        return True
                    elif status == "failed":
                        error = status_data.get("error", "Unknown error")
                        logger.error(f"Job failed: {error}")
                        return False
                
                # Wait before checking again
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error checking job status: {e}")
                time.sleep(5)
        
        logger.error(f"Job timed out after {timeout} seconds")
        return False

    def create_video(self, image_paths: List[str], audio_path: str, story: str, timestamp: str, output_path: str) -> str:
        """Create video using the GPU worker - matches the expected interface."""
        try:
            logger.info(f"Creating video with GPU worker at {self.worker_url}")
            logger.info(f"Image paths: {image_paths}")
            logger.info(f"Audio path: {audio_path}")
            logger.info(f"Output path: {output_path}")
            
            # Use the updated process_video method
            success = self.process_video(image_paths, output_path, audio_path, story)
            
            if success:
                logger.info(f"Video created successfully at {output_path}")
                return output_path
            else:
                raise Exception("GPU worker video processing failed")
                
        except Exception as e:
            logger.error(f"Error in create_video: {e}")
            raise 