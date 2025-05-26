from fastapi import FastAPI, BackgroundTasks, HTTPException
import subprocess
import logging
import os
import json
from typing import Dict, Any

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if NVIDIA GPU is available
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=503, detail="NVIDIA GPU not available")
        return {"status": "healthy", "gpu": "available"}
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/process")
async def process_video(job_data: Dict[str, Any], background_tasks: BackgroundTasks):
    """Process a video job"""
    try:
        # Validate required fields
        required_fields = ["input", "output"]
        for field in required_fields:
            if field not in job_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Validate input file exists
        if not os.path.exists(job_data["input"]):
            raise HTTPException(status_code=404, detail=f"Input file not found: {job_data['input']}")
        
        # Add job to background tasks
        background_tasks.add_task(render_video, job_data)
        return {"status": "processing", "job_id": job_data.get("job_id", "unknown")}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error processing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def render_video(job_data: Dict[str, Any]):
    """Render video using NVIDIA GPU acceleration"""
    try:
        logging.info(f"Rendering video: {job_data}")
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(job_data["output"])
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Run ffmpeg with NVIDIA GPU acceleration
        result = subprocess.run([
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-i", job_data["input"],
            "-c:v", "h264_nvenc",
            "-preset", "fast",
            job_data["output"]
        ], capture_output=True, text=True, check=True)
        
        logging.info(f"Video rendered successfully: {job_data['output']}")
        
        # Save job status
        status_file = f"{job_data['output']}.status"
        with open(status_file, "w") as f:
            json.dump({
                "status": "completed",
                "job_id": job_data.get("job_id", "unknown"),
                "output": job_data["output"]
            }, f)
            
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg error: {e.stderr}"
        logging.error(error_msg)
        # Save error status
        status_file = f"{job_data['output']}.status"
        with open(status_file, "w") as f:
            json.dump({
                "status": "failed",
                "job_id": job_data.get("job_id", "unknown"),
                "error": error_msg
            }, f)
    except Exception as e:
        error_msg = f"Error rendering video: {str(e)}"
        logging.error(error_msg)
        # Save error status
        status_file = f"{job_data['output']}.status"
        with open(status_file, "w") as f:
            json.dump({
                "status": "failed",
                "job_id": job_data.get("job_id", "unknown"),
                "error": error_msg
            }, f) 