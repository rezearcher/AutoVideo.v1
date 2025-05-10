import os
import sys
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
from story_generator import generate_story, extract_image_prompts
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from video_creator import create_video
from output_manager import OutputManager
from topic_manager import TopicManager
from youtube_uploader import upload_video, YouTubeConfig
from flask import Flask, jsonify

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Load environment variables
logging.info("Loading environment variables...")
load_dotenv()
logging.info("Environment variables loaded")

# Initialize Flask app
logging.info("Initializing Flask application...")
app = Flask(__name__)

# Global state variables
is_generating = False
is_initialized = False
last_generation_time = None
last_generation_status = None
current_phase = None
current_progress = None
current_phase_progress = None
error_message = None
output_manager = None
init_thread = None
startup_time = time.time()

def background_initialization():
    """Perform heavy initialization in the background."""
    global is_initialized
    try:
        logging.info("Starting background initialization...")
        
        # Create necessary directories
        logging.info("Creating application directories...")
        os.makedirs("/app/output", exist_ok=True)
        os.makedirs("/app/secrets", exist_ok=True)
        logging.info("Application directories created successfully")
        
        # Check environment variables
        logging.info("Checking environment variables...")
        required_vars = [
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            "ELAI_API_KEY",
            "DID_API_KEY",
            "IMGUR_CLIENT_ID",
            "IMGUR_CLIENT_SECRET",
            "ELEVENLABS_API_KEY",
            "PEXELS_API_KEY",
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_PROJECT_ID"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            logging.warning(f"Missing environment variables: {', '.join(missing_vars)}")
        
        is_initialized = True
        logging.info(f"Background initialization completed successfully in {time.time() - startup_time:.2f} seconds")
        
    except Exception as e:
        logging.error(f"Failed to initialize application: {str(e)}")

@app.route('/health')
def health_check():
    """Health check endpoint that always returns 200 when the app is running."""
    return jsonify({
        "status": "healthy",
        "initialized": is_initialized,
        "uptime": time.time() - startup_time if startup_time else 0,
        "startup_time": startup_time
    }), 200

@app.route('/')
def root():
    """Root endpoint that returns basic status."""
    return jsonify({
        "status": "running",
        "initialized": is_initialized,
        "uptime": time.time() - startup_time if startup_time else 0,
        "startup_time": startup_time
    }), 200

@app.route('/status')
def status():
    """Get the current status of the video generation process."""
    return jsonify({
        'is_generating': is_generating,
        'is_initialized': is_initialized,
        'last_generation_status': last_generation_status,
        'last_generation_time': last_generation_time.isoformat() if last_generation_time else None,
        'current_phase': current_phase,
        'current_progress': current_progress,
        'current_phase_progress': current_phase_progress,
        'error_message': error_message,
        'uptime': time.time() - startup_time if startup_time else 0,
        'startup_time': startup_time
    })

# Start background initialization
init_thread = threading.Thread(target=background_initialization)
init_thread.daemon = True
init_thread.start()

# Create the WSGI application instance for gunicorn
application = app

if __name__ == "__main__":
    # Get port from environment variable
    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0"
    
    logging.info(f"Starting Flask development server on {host}:{port}")
    try:
        app.run(host=host, port=port)
    except Exception as e:
        logging.error(f"Failed to start Flask server: {str(e)}")
        sys.exit(1)
