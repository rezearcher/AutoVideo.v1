import os
import logging
import asyncio
from flask import Flask, jsonify
from worker_client import WorkerClient
from story_generator import generate_story
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from youtube_uploader import upload_video
from datetime import datetime
from timing_metrics import TimingMetrics
from flask_async import FlaskAsync

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FlaskAsync(__name__)
is_generating = False
is_initialized = False
timing_metrics = TimingMetrics()

async def generate_video():
    """Generate a video using the GPU worker."""
    global is_generating
    try:
        is_generating = True
        timing_metrics.start_pipeline()
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"/app/output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate content
        timing_metrics.start_phase("story_generation")
        story = await generate_story()
        timing_metrics.end_phase()
        
        timing_metrics.start_phase("image_generation")
        image_paths = await generate_images(story, output_dir)
        timing_metrics.end_phase()
        
        timing_metrics.start_phase("voiceover_generation")
        audio_path = await generate_voiceover(story, output_dir)
        timing_metrics.end_phase()
        
        # Create worker
        timing_metrics.start_phase("worker_creation")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        worker_url = await WorkerClient.create_worker(project_id)
        if not worker_url:
            raise Exception("Failed to create GPU worker")
        timing_metrics.end_phase()
        
        # Process video using worker
        timing_metrics.start_phase("video_processing")
        worker = WorkerClient(worker_url)
        output_path = f"{output_dir}/final_video.mp4"
        success = await worker.process_video(image_paths, output_path, audio_path)
        timing_metrics.end_phase()
        
        if not success:
            raise Exception("Video processing failed")
        
        # Upload to YouTube
        timing_metrics.start_phase("youtube_upload")
        await upload_video(output_path, story)
        timing_metrics.end_phase()
        
        logger.info("Video generation and upload completed successfully")
        
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        raise
    finally:
        timing_metrics.end_pipeline()
        is_generating = False

@app.route('/generate', methods=['POST'])
async def start_generation():
    """Start video generation."""
    global is_generating
    if is_generating:
        return jsonify({"status": "already_generating"}), 409
    
    asyncio.create_task(generate_video())
    return jsonify({"status": "started"}), 202

@app.route('/status', methods=['GET'])
async def get_status():
    """Get the current generation status."""
    metrics = timing_metrics.get_metrics()
    return jsonify({
        "is_generating": is_generating,
        "is_initialized": is_initialized,
        "last_generation_status": "in_progress" if is_generating else "idle",
        "last_generation_time": datetime.now().isoformat() if is_generating else None,
        "timing_metrics": {
            "total_duration": metrics["total_duration"],
            "phase_times": metrics["phase_times"],
            "current_phase": metrics["current_phase"],
            "current_phase_duration": metrics["current_phase_duration"]
        }
    })

@app.route('/health')
async def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200

def initialize_app():
    """Initialize the application."""
    global is_initialized
    try:
        logger.info("Starting application initialization...")
        
        # Create necessary directories
        logger.info("Creating application directories...")
        os.makedirs("/app/output", exist_ok=True)
        os.makedirs("/app/secrets", exist_ok=True)
        logger.info("Application directories created successfully")
        
        # Check environment variables
        logger.info("Checking environment variables...")
        required_vars = [
            "OPENAI_API_KEY",
            "ELEVENLABS_API_KEY",
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_PROJECT_ID",
            "GOOGLE_CLOUD_PROJECT"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        logger.info("Application initialization completed successfully")
        is_initialized = True
        
    except Exception as e:
        logger.error(f"Error initializing application: {str(e)}")
        raise

# Initialize the application
initialize_app()

# Create WSGI application instance for Gunicorn
application = app

if __name__ == "__main__":
    # Start Flask server in development mode
    app.run(host='0.0.0.0', port=8080)
