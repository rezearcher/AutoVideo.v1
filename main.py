import os
import logging
from flask import Flask, jsonify, request
from worker_client import WorkerClient
from story_generator import generate_story
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from youtube_uploader import upload_video
from datetime import datetime
import threading
import time
from timing_metrics import TimingMetrics

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variables
is_generating = False
is_initialized = False
last_generation_time = None
last_generation_status = None
timing_metrics = TimingMetrics()

def initialize_app():
    """Initialize the application and check required environment variables."""
    logger.info("Starting application initialization...")
    
    # Create necessary directories
    logger.info("Creating application directories...")
    os.makedirs('output', exist_ok=True)
    os.makedirs('secrets', exist_ok=True)
    os.makedirs('fonts', exist_ok=True)
    logger.info("Application directories created successfully")
    
    # Check required environment variables
    logger.info("Checking environment variables...")
    required_vars = ['GOOGLE_CLOUD_PROJECT']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(f"Error initializing application: {error_msg}")
        raise ValueError(error_msg)
    
    logger.info("Application initialized successfully")
    return True

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})

@app.route('/status')
def status():
    """Get the current status of video generation."""
    return jsonify({
        "is_generating": is_generating,
        "is_initialized": is_initialized,
        "last_generation_time": last_generation_time,
        "last_generation_status": last_generation_status,
        "timing_metrics": timing_metrics.get_metrics()
    })

def generate_video_thread():
    """Background thread for video generation."""
    global is_generating, last_generation_status
    
    try:
        # Start timing
        timing_metrics.start_phase("total")
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"/app/output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate content
        timing_metrics.start_phase("story_generation")
        story = generate_story("Create a video about the history of artificial intelligence, focusing on key milestones and breakthroughs")
        timing_metrics.end_phase()
        
        timing_metrics.start_phase("image_generation")
        image_paths = generate_images(story, output_dir)
        timing_metrics.end_phase()
        
        timing_metrics.start_phase("voiceover_generation")
        audio_path = generate_voiceover(story, output_dir)
        timing_metrics.end_phase()
        
        # Create worker
        timing_metrics.start_phase("worker_creation")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        worker_url = WorkerClient.create_worker(project_id)
        if not worker_url:
            raise Exception("Failed to create GPU worker")
        timing_metrics.end_phase()
        
        # Process video using worker
        timing_metrics.start_phase("video_processing")
        worker = WorkerClient(worker_url)
        output_path = f"{output_dir}/final_video.mp4"
        success = worker.process_video(image_paths, output_path, audio_path)
        timing_metrics.end_phase()
        
        if not success:
            raise Exception("Video processing failed")
        
        # Upload to YouTube
        timing_metrics.start_phase("youtube_upload")
        upload_video(output_path, story)
        timing_metrics.end_phase()
        
        logger.info("Video generation and upload completed successfully")
        
        last_generation_status = "completed"
    except Exception as e:
        logger.error(f"Error generating video: {str(e)}")
        last_generation_status = f"error: {str(e)}"
    finally:
        is_generating = False
        timing_metrics.end_phase("total")

# Initialize the application
try:
    is_initialized = initialize_app()
except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    is_initialized = False

# Expose the WSGI application
application = app

if __name__ == "__main__":
    # Start video generation in a background thread
    thread = threading.Thread(target=generate_video_thread)
    thread.daemon = True
    thread.start()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=8080)
