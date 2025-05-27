from fastapi import FastAPI, BackgroundTasks, HTTPException
import subprocess
import logging
import os
import json
import tempfile
import shutil
from typing import Dict, Any, List
from moviepy.editor import VideoFileClip, ImageClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip
import numpy as np
from caption_generator import create_caption_images, add_captions_to_video

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/process")
async def process_video(job_data: Dict[str, Any], background_tasks: BackgroundTasks):
    """Process a video job with GPU acceleration and captions"""
    try:
        # Validate required fields for image-based video creation
        if "image_paths" in job_data and "audio_path" in job_data:
            # New video creation from images and audio
            required_fields = ["image_paths", "audio_path", "output_path"]
            for field in required_fields:
                if field not in job_data:
                    raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
            
            # Validate image files exist
            for image_path in job_data["image_paths"]:
                if not os.path.exists(image_path):
                    raise HTTPException(status_code=404, detail=f"Image file not found: {image_path}")
            
            # Validate audio file exists
            if not os.path.exists(job_data["audio_path"]):
                raise HTTPException(status_code=404, detail=f"Audio file not found: {job_data['audio_path']}")
                
        else:
            # Legacy video processing
            required_fields = ["input", "output"]
            for field in required_fields:
                if field not in job_data:
                    raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
            
            # Validate input file exists
            if not os.path.exists(job_data["input"]):
                raise HTTPException(status_code=404, detail=f"Input file not found: {job_data['input']}")
        
        # Add job to background tasks
        background_tasks.add_task(process_video_job, job_data)
        return {"status": "processing", "job_id": job_data.get("job_id", "unknown")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def process_video_job(job_data: Dict[str, Any]):
    """Main video processing function"""
    try:
        if "image_paths" in job_data and "audio_path" in job_data:
            # Create video from images and audio with captions
            create_video_from_images_gpu(job_data)
        else:
            # Legacy video processing
            render_video_legacy(job_data)
    except Exception as e:
        logger.error(f"Error in process_video_job: {e}")
        # Save error status
        save_job_status(job_data, "failed", str(e))

def create_video_from_images_gpu(job_data: Dict[str, Any]):
    """Create video from images and audio using GPU acceleration with captions"""
    try:
        logger.info(f"Creating video from images with GPU acceleration: {job_data}")
        
        image_paths = job_data["image_paths"]
        audio_path = job_data["audio_path"]
        output_path = job_data["output_path"]
        story = job_data.get("story", "")
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create temporary video without captions first
        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        
        try:
            # Create clips from images
            logger.info("Creating video clips from images...")
            clips = []
            
            for image_path in image_paths:
                clip = ImageClip(image_path).set_duration(5)  # 5 seconds per image
                clips.append(clip)
            
            # Concatenate all clips
            logger.info("Concatenating video clips...")
            final_clip = concatenate_videoclips(clips)
            
            # Add audio
            logger.info("Adding audio to video...")
            audio = AudioFileClip(audio_path)
            final_clip = final_clip.set_audio(audio)
            
            # Write initial video with GPU encoding
            logger.info(f"Writing video with GPU encoding to: {temp_video_path}")
            final_clip.write_videofile(
                temp_video_path,
                fps=24,
                codec='libx264',
                ffmpeg_params=['-hwaccel', 'cuda', '-c:v', 'h264_nvenc', '-preset', 'fast']
            )
            
            # Clean up clips
            final_clip.close()
            for clip in clips:
                clip.close()
            audio.close()
            
            # Add captions if story is provided
            if story:
                logger.info("Adding captions to video...")
                try:
                    # Create caption images
                    caption_images = create_caption_images(story)
                    
                    # Add captions to video
                    add_captions_to_video(temp_video_path, caption_images, output_path)
                    
                    # Remove temporary video
                    if os.path.exists(temp_video_path):
                        os.remove(temp_video_path)
                    
                    logger.info("Captions added successfully")
                except Exception as caption_error:
                    logger.error(f"Error adding captions: {caption_error}")
                    # Use video without captions
                    shutil.move(temp_video_path, output_path)
            else:
                # No captions needed, just move the temp video
                shutil.move(temp_video_path, output_path)
            
            logger.info(f"Video created successfully: {output_path}")
            save_job_status(job_data, "completed")
            
        except Exception as e:
            # Clean up temporary files
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            raise e
            
    except Exception as e:
        error_msg = f"Error creating video from images: {str(e)}"
        logger.error(error_msg)
        save_job_status(job_data, "failed", error_msg)

def render_video_legacy(job_data: Dict[str, Any]):
    """Legacy video rendering using NVIDIA GPU acceleration"""
    try:
        logger.info(f"Legacy rendering video: {job_data}")
        
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
        
        logger.info(f"Video rendered successfully: {job_data['output']}")
        save_job_status(job_data, "completed")
            
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg error: {e.stderr}"
        logger.error(error_msg)
        save_job_status(job_data, "failed", error_msg)
    except Exception as e:
        error_msg = f"Error rendering video: {str(e)}"
        logger.error(error_msg)
        save_job_status(job_data, "failed", error_msg)

def save_job_status(job_data: Dict[str, Any], status: str, error: str = None):
    """Save job status to file"""
    try:
        output_path = job_data.get("output_path", job_data.get("output", ""))
        status_file = f"{output_path}.status"
        
        status_data = {
            "status": status,
            "job_id": job_data.get("job_id", "unknown"),
            "output": output_path
        }
        
        if error:
            status_data["error"] = error
            
        with open(status_file, "w") as f:
            json.dump(status_data, f)
            
    except Exception as e:
        logger.error(f"Error saving job status: {e}") 