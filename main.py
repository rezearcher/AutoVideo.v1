import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from story_generator import generate_story, extract_image_prompts
from image_generator import generate_images
from voiceover_generator import generate_voiceover
from video_creator import create_video
from output_manager import OutputManager
from topic_manager import TopicManager

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('output/logs/error.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    try:
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
        output_manager.save_text(story, "story.txt")
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
        
        # Clean up temporary files
        output_manager.cleanup()
        logging.info("Temporary files cleaned up")
        
        logging.info("Video generation completed successfully!")
        
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
