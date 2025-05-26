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
        """Create a new GPU worker instance."""
        try:
            # Deploy worker using gcloud
            cmd = [
                "gcloud", "run", "deploy", "gpu-worker",
                "--image", f"us-central1-docker.pkg.dev/{project_id}/av-app/gpu-worker:latest",
                "--platform", "managed",
                "--region", "us-central1",
                "--allow-unauthenticated",
                "--memory", "4Gi",
                "--cpu", "2",
                "--min-instances", "0",
                "--max-instances", "1",
                "--port", "8080"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to create worker: {result.stderr}")
                return None
                
            # Extract service URL from output
            for line in result.stdout.split('\n'):
                if "Service URL:" in line:
                    return line.split("Service URL:")[1].strip()
                    
            logger.error("Could not find service URL in deployment output")
            return None
            
        except Exception as e:
            logger.error(f"Error creating worker: {e}")
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