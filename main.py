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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Flask app
app = Flask(__name__)

# Global state
is_generating = False
last_generation_time = None
last_generation_status = None

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/status')
def status():
    global is_generating, last_generation_time, last_generation_status
    return jsonify({
        "is_generating": is_generating,
        "last_generation_time": last_generation_time,
        "last_generation_status": last_generation_status
    }), 200

def generate_video():
    global is_generating, last_generation_time, last_generation_status
    try:
        is_generating = True
        last_generation_time = datetime.now().isoformat()
        last_generation_status = "in_progress"
        
        # Initialize output manager and create run directory
        output_manager = OutputManager()
        run_dir = output_manager.create_run_directory()
        
        # Initialize topic manager
        topic_manager = TopicManager()
        
        # Get next topic
        story_prompt = topic_manager.get_next_topic()
        logging.info(f"Selected topic: {story_prompt}")
        
        # Generate story
        logging.info("Generating story...")
        story_result = generate_story(story_prompt)
        if not story_result:
            raise Exception("Failed to generate story")
        story, _ = story_result  # Unpack the tuple, ignoring the prompt
            
        # Save story
        story_path = output_manager.get_path("story.txt", subdir='text')
        output_manager.save_text(story, story_path)
        logging.info("Story saved successfully")
        
        # Extract image prompts
        logging.info("Extracting image prompts...")
        image_prompts = extract_image_prompts(story)
        if not image_prompts:
            raise Exception("Failed to extract image prompts")
            
        # Generate images
        logging.info("Generating images...")
        image_paths = []
        for i, prompt in enumerate(image_prompts):
            image_path = output_manager.get_path(f"image_{i+1}.png", subdir='images')
            output_manager.ensure_dir_exists(os.path.dirname(image_path))
            generated_path = generate_images(prompt, image_path)
            if not generated_path:
                raise Exception(f"Failed to generate image {i+1}")
            image_paths.append(generated_path)
            logging.info(f"Image {i+1} saved to: {generated_path}")
            
        # Generate voiceover
        logging.info("Generating voiceover...")
        voiceover_path = output_manager.get_path("voiceover.mp3", subdir='audio')
        output_manager.ensure_dir_exists(os.path.dirname(voiceover_path))
        voiceover_path = generate_voiceover(story, voiceover_path)
        if not voiceover_path:
            raise Exception("Failed to generate voiceover")
        logging.info(f"Voiceover saved to: {voiceover_path}")
        
        # Create video
        logging.info("Creating video...")
        video_path = output_manager.get_path("final_video.mp4", subdir='video')
        output_manager.ensure_dir_exists(os.path.dirname(video_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        create_video(image_paths, voiceover_path, story, timestamp, output_path=video_path)
        logging.info(f"Video saved to: {video_path}")
        
        # Upload to YouTube
        title = f"AI Generated Story: {story_prompt}"
        description = f"An AI-generated story video.\n\n{story[:500]}..."  # First 500 chars of story
        tags = ["AI", "story", "generated", "creative"]
        
        logging.info("Uploading video to YouTube...")
        if upload_to_youtube(video_path):
            logging.info("Video uploaded successfully!")
            last_generation_status = "success"
        else:
            logging.error("Failed to upload video to YouTube")
            last_generation_status = "failed_upload"
        
        # Clean up temporary files
        output_manager.cleanup()
        logging.info("Temporary files cleaned up")
        
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        last_generation_status = f"error: {str(e)}"
        raise
    finally:
        is_generating = False

def upload_to_youtube(video_path):
    """Upload video to YouTube."""
    try:
        from youtube_uploader.uploader import upload_video
        
        # Generate a title and description
        title = f"AI Generated Story Video - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        description = "An AI-generated story video created using OpenAI's GPT and DALL-E models."
        
        # Upload the video
        video_id = upload_video(
            video_path=video_path,
            title=title,
            description=description,
            privacy_status="public"  # Changed to public by default
        )
        
        if video_id:
            video_url = f"https://youtu.be/{video_id}"
            logging.info(f"Video uploaded successfully! Video ID: {video_id}")
            logging.info(f"Watch it here: {video_url}")
            return True
        else:
            logging.error("Failed to upload video to YouTube")
            return False
            
    except Exception as e:
        logging.error(f"Error uploading to YouTube: {str(e)}")
        return False

def start_video_generation():
    """Start video generation in a background thread."""
    thread = threading.Thread(target=generate_video)
    thread.daemon = True
    thread.start()
    return thread

if __name__ == "__main__":
    # Start video generation in background
    start_video_generation()
    
    # Start Flask app
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
