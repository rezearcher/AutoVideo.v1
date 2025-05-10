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

@app.route('/health')
def health_check():
    """Health check endpoint that always returns 200 when the app is running."""
    logging.info("Health check endpoint called")
    return jsonify({"status": "healthy"}), 200

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
        'error_message': error_message
    })

@app.route('/generate', methods=['POST'])
def start_generation():
    """Start video generation in a background thread."""
    global is_generating
    if is_generating:
        return jsonify({"status": "already_generating"}), 409
    
    thread = threading.Thread(target=generate_video)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"}), 202

def generate_video():
    """Generate a video with the current configuration."""
    global is_generating, last_generation_time, last_generation_status, current_phase, current_progress, current_phase_progress, error_message, output_manager
    
    try:
        is_generating = True
        last_generation_time = datetime.now()
        last_generation_status = "in_progress"
        error_message = None
        
        # Initialize output manager and create run directory
        output_manager = OutputManager()
        run_dir = output_manager.create_run_directory()
        
        # Initialize topic manager
        topic_manager = TopicManager()
        
        # Get next topic
        story_prompt = topic_manager.get_next_topic()
        logging.info(f"Selected topic: {story_prompt}")
        
        # Story generation phase
        current_phase = "story_generation"
        current_progress = 0
        current_phase_progress = 0
        story_result = generate_story(story_prompt)
        if not story_result:
            raise Exception("Failed to generate story")
        story, _ = story_result
        current_phase_progress = 100
        
        # Save story
        story_path = output_manager.get_path("story.txt", subdir='text')
        output_manager.save_text(story, story_path)
        logging.info("Story saved successfully")
        
        # Image generation phase
        current_phase = "image_generation"
        current_progress = 20
        current_phase_progress = 0
        image_prompts = extract_image_prompts(story)
        if not image_prompts:
            raise Exception("Failed to extract image prompts")
            
        image_paths = []
        for i, prompt in enumerate(image_prompts):
            image_path = output_manager.get_path(f"image_{i+1}.png", subdir='images')
            output_manager.ensure_dir_exists(os.path.dirname(image_path))
            generated_path = generate_images(prompt, image_path)
            if not generated_path:
                raise Exception(f"Failed to generate image {i+1}")
            image_paths.append(generated_path)
            current_phase_progress = (i + 1) * 100 // len(image_prompts)
            logging.info(f"Image {i+1} saved to: {generated_path}")
        
        # Voiceover generation phase
        current_phase = "voiceover_generation"
        current_progress = 40
        current_phase_progress = 0
        logging.info("Generating voiceover...")
        voiceover_path = output_manager.get_path("voiceover.mp3", subdir='audio')
        output_manager.ensure_dir_exists(os.path.dirname(voiceover_path))
        voiceover_path = generate_voiceover(story, voiceover_path)
        if not voiceover_path:
            raise Exception("Failed to generate voiceover")
        current_phase_progress = 100
        logging.info(f"Voiceover saved to: {voiceover_path}")
        
        # Video creation phase
        current_phase = "video_creation"
        current_progress = 60
        current_phase_progress = 0
        logging.info("Creating video...")
        video_path = output_manager.get_path("final_video.mp4", subdir='video')
        output_manager.ensure_dir_exists(os.path.dirname(video_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        create_video(image_paths, voiceover_path, story, timestamp, output_path=video_path)
        current_phase_progress = 100
        logging.info(f"Video saved to: {video_path}")
        
        # YouTube upload phase
        current_phase = "youtube_upload"
        current_progress = 80
        current_phase_progress = 0
        title = f"AI Generated Story: {story_prompt}"
        description = f"An AI-generated story video.\n\n{story[:500]}..."  # First 500 chars of story
        tags = ["AI", "story", "generated", "creative"]
        
        logging.info("Uploading video to YouTube...")
        video_id = upload_video(video_path, title, description, tags)
        if video_id:
            video_url = f"https://youtu.be/{video_id}"
            logging.info(f"Video uploaded successfully! Video ID: {video_id}")
            logging.info(f"Watch it here: {video_url}")
        else:
            logging.error("Failed to upload video to YouTube")
        
        current_phase_progress = 100
        current_progress = 100
        last_generation_status = "completed"
        logging.info("Video generation completed successfully")
        
    except Exception as e:
        error_message = str(e)
        last_generation_status = "failed"
        logging.error(f"Error generating video: {error_message}")
    finally:
        is_generating = False
        if output_manager:
            output_manager.cleanup()

def initialize_app():
    """Initialize the application."""
    global is_initialized
    try:
        logging.info("Starting application initialization...")
        
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
            # Don't raise exception, just log warning
        
        is_initialized = True
        logging.info("Application initialization completed successfully")
        
    except Exception as e:
        logging.error(f"Failed to initialize application: {str(e)}")
        # Don't raise exception, just log error

def run_video_generation():
    """Run the video generation pipeline on startup and exit after completion."""
    global is_generating
    try:
        # Read prompt from environment variable or fallback file
        prompt = os.getenv("VIDEO_PROMPT")
        if not prompt:
            prompt_file = "/app/prompt.txt"
            if os.path.exists(prompt_file):
                with open(prompt_file, "r") as f:
                    prompt = f.read().strip()
            else:
                logging.error("No prompt provided via VIDEO_PROMPT or /app/prompt.txt")
                sys.exit(1)
        
        logging.info(f"Starting video generation with prompt: {prompt}")
        generate_video()
        logging.info("Video generation completed, exiting container")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Error in run_video_generation: {str(e)}")
        sys.exit(1)

# Initialize the application
logging.info("Starting application...")
initialize_app()
logging.info("Application started successfully")

# Create the WSGI application instance for gunicorn
logging.info("Creating WSGI application instance...")
application = app
logging.info("WSGI application instance created")

if __name__ == "__main__":
    # Start Flask server in a background thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run video generation in the main thread
    try:
        logging.info("Starting video generation...")
        generate_video()  # This will use TopicManager to get the prompt
        logging.info("Video generation completed, exiting container")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Error in video generation: {str(e)}")
        sys.exit(1)
