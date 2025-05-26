import os
import logging
from flask import Flask, jsonify, request
from worker_client import WorkerClient
from story_generator import generate_story, extract_image_prompts
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from youtube_uploader import upload_video
from datetime import datetime
import threading
import time
from timing_metrics import TimingMetrics
from topic_manager import TopicManager

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
topic_manager = None

def initialize_app():
    """Initialize the application and check required environment variables."""
    logger.info("Starting application initialization...")
    
    try:
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
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}", exc_info=True)
        raise

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

@app.route('/generate', methods=['POST'])
def start_generation():
    """Start the video generation process."""
    global is_generating
    
    if is_generating:
        return jsonify({"error": "Video generation already in progress"}), 409
    
    if not is_initialized:
        return jsonify({"error": "Application not properly initialized"}), 500
    
    # Start video generation in a background thread
    thread = threading.Thread(target=generate_video_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Video generation started"})

def generate_video_thread():
    """Background thread for video generation."""
    global is_generating, last_generation_status, topic_manager
    
    try:
        is_generating = True
        # Start timing
        timing_metrics.start_pipeline()
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"/app/output/run_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize topic manager and get next topic
        if topic_manager is None:
            topic_manager = TopicManager()
        story_prompt = topic_manager.get_next_topic()
        
        # Generate content
        timing_metrics.start_phase("story_generation")
        story, prompt = generate_story(story_prompt)
        timing_metrics.end_phase()
        
        # Extract image prompts from the story
        image_prompts = extract_image_prompts(story)
        
        timing_metrics.start_phase("image_generation")
        image_paths = generate_images(image_prompts, output_dir)
        timing_metrics.end_phase()
        
        timing_metrics.start_phase("voiceover_generation")
        audio_path = os.path.join(output_dir, "voiceover.mp3")
        generate_voiceover(story, audio_path)
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
        # Extract title and description from story
        story_lines = story.split('\n')
        title = story_lines[0].replace('Title: ', '')
        description = story_lines[1].replace('Description: ', '')
        # Add the full story as additional context
        description += "\n\nFull Story:\n" + "\n".join(story_lines[2:])
        upload_video(output_path, title, description)
        timing_metrics.end_phase()
        
        logger.info("Video generation and upload completed successfully")
        
        last_generation_status = "completed"
    except Exception as e:
        logger.error(f"Error generating video: {str(e)}")
        last_generation_status = f"error: {str(e)}"
    finally:
        is_generating = False
        timing_metrics.end_pipeline()

# Initialize the application
try:
    is_initialized = initialize_app()
except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    is_initialized = False

# Expose the WSGI application
application = app

if __name__ == "__main__":
    # Start Flask server
    app.run(host='0.0.0.0', port=8080)
