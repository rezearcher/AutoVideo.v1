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

    def process_video(self, image_paths: List[str], output_path: str, audio_path: str) -> bool:
        """Process video using the GPU worker."""
        import requests
        
        try:
            # Prepare job data
            job_data = {
                "image_paths": image_paths,
                "output_path": output_path,
                "audio_path": audio_path
            }
            
            # Send job to worker
            response = requests.post(f"{self.worker_url}/process", json=job_data)
            if response.status_code != 200:
                logger.error(f"Worker returned status {response.status_code}")
                return False
                
            result = response.json()
            return result.get("status") == "completed"
                
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return False 