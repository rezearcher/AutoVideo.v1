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
from flask import Flask, jsonify, request

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
    # Calculate runtime if generation is in progress
    runtime = None
    if is_generating and last_generation_time:
        runtime = (datetime.now() - last_generation_time).total_seconds()
    
    # Get phase description
    phase_descriptions = {
        "story_generation": "Generating story and image prompts",
        "image_generation": "Generating images from prompts",
        "voiceover_generation": "Generating voiceover audio",
        "video_creation": "Creating final video with captions"
    }
    
    phase_description = phase_descriptions.get(current_phase, current_phase)
    
    return jsonify({
        'is_generating': is_generating,
        'is_initialized': is_initialized,
        'last_generation_status': last_generation_status,
        'last_generation_time': last_generation_time.isoformat() if last_generation_time else None,
        'current_phase': current_phase,
        'current_phase_description': phase_description,
        'current_progress': current_progress,
        'current_phase_progress': current_phase_progress,
        'error_message': error_message,
        'runtime_seconds': runtime,
        'uptime': time.time() - startup_time if startup_time else 0,
        'startup_time': startup_time
    })

@app.route('/generate', methods=['POST'])
def start_generation():
    """Start video generation with the provided prompt."""
    global is_generating
    
    if is_generating:
        return jsonify({
            'error': 'Video generation already in progress',
            'status': 'busy'
        }), 409
    
    if not request.json or 'prompt' not in request.json:
        return jsonify({
            'error': 'Missing prompt in request body',
            'status': 'error'
        }), 400
    
    prompt = request.json['prompt']
    
    try:
        # Start generation in a background thread
        thread = threading.Thread(target=generate_video, args=(prompt,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': 'Video generation started',
            'prompt': prompt
        }), 202
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# Start background initialization
init_thread = threading.Thread(target=background_initialization)
init_thread.daemon = True
init_thread.start()

# Create the WSGI application instance for gunicorn
application = app

def update_generation_status(phase, progress=None, phase_progress=None, error=None):
    """Update the current status of the video generation process."""
    global current_phase, current_progress, current_phase_progress, error_message
    current_phase = phase
    current_progress = progress
    current_phase_progress = phase_progress
    error_message = error

def generate_video(prompt):
    """Generate a video from a prompt."""
    global is_generating, last_generation_time, last_generation_status
    
    try:
        is_generating = True
        last_generation_time = datetime.now()
        last_generation_status = "started"
        
        # Create timestamp for unique file names
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Create output directories
        output_dir = os.path.join('output', timestamp)
        os.makedirs(output_dir, exist_ok=True)

        # Step 1: Generate story and image prompts
        update_generation_status("story_generation", progress=0, phase_progress=0)
        logging.info("Step 1: Generating story...")
        story, prompt = generate_story(prompt)
        image_prompts = extract_image_prompts(story)
        update_generation_status("story_generation", progress=25, phase_progress=100)

        # Step 2: Generate and save images
        update_generation_status("image_generation", progress=25, phase_progress=0)
        logging.info("Step 2: Generating images...")
        total_images = len(image_prompts)
        for i, prompt in enumerate(image_prompts):
            images = generate_images([prompt])
            image_paths = save_images(images, timestamp)
            phase_progress = int((i + 1) / total_images * 100)
            update_generation_status("image_generation", progress=25 + (25 * phase_progress / 100), phase_progress=phase_progress)
        update_generation_status("image_generation", progress=50, phase_progress=100)

        # Step 3: Generate audio
        update_generation_status("voiceover_generation", progress=50, phase_progress=0)
        logging.info("Step 3: Generating audio...")
        audio_path = os.path.join(output_dir, 'voiceover.m4a')
        generate_voiceover(story, audio_path)
        update_generation_status("voiceover_generation", progress=75, phase_progress=100)

        # Step 4: Create video
        update_generation_status("video_creation", progress=75, phase_progress=0)
        logging.info("Step 4: Creating video...")
        video_path = os.path.join(output_dir, 'final_video.mp4')
        create_video(image_paths, audio_path, story, timestamp, video_path)
        update_generation_status("video_creation", progress=100, phase_progress=100)
        
        last_generation_status = "completed"
        logging.info(f"✅ Video pipeline completed successfully! Output at: {video_path}")
        return video_path
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"❌ Error in video pipeline: {error_msg}")
        last_generation_status = "failed"
        update_generation_status(None, error=error_msg)
        raise
        
    finally:
        is_generating = False

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
