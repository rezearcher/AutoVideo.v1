import os
import logging
import openai  # Using openai package version 0.28.0
from dotenv import load_dotenv
from datetime import datetime
import time
import sys

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')

def generate_story(prompt, timeout=60):
    """
    Generate a story from a prompt with a timeout.
    
    Args:
        prompt (str): The story prompt
        timeout (int): Maximum time in seconds to wait for story generation
        
    Returns:
        tuple: (story, prompt)
    """
    start_time = time.time()
    max_retries = 3
    retry_count = 0
    
    logging.info(f"Starting story generation with prompt: {prompt}")
    
    while retry_count < max_retries:
        if time.time() - start_time > timeout:
            logging.error("Story generation timed out")
            raise Exception("Story generation timed out")
            
        try:
            logging.info("Sending request to OpenAI API...")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """You are a creative storyteller. When writing a story, follow this format:
1. Title: A catchy, engaging title that captures the essence of the story
2. Description: A brief 2-3 sentence summary that hooks the reader
3. Story: The full story content

Make sure the title and description are compelling and accurately represent the story's content."""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            story = response.choices[0].message.content.strip()
            logging.info("Story generated successfully")
            logging.debug(f"Generated story: {story}")
            
            return story, prompt
            
        except Exception as e:
            logging.error(f"Error generating story: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed to generate story after {max_retries} attempts: {str(e)}")
            time.sleep(1)

def extract_image_prompts(story, num_scenes=5):
    """Extract image prompts from the story."""
    try:
        logging.info("Extracting image prompts from story...")
        
        prompt = f"""
        Given this story, create {num_scenes} detailed image prompts that capture key scenes.
        Make each prompt detailed and descriptive for image generation.
        Story: {story}
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at creating detailed image prompts from stories."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        prompts_text = response.choices[0].message.content.strip()
        prompts = [p.strip() for p in prompts_text.split('\n') if p.strip()]
        logging.info(f"Generated {len(prompts)} image prompts")
        return prompts[:num_scenes]
        
    except Exception as e:
        logging.error(f"Error extracting image prompts: {str(e)}")
        return None

def save_story_with_image_prompts(story, prompt, image_prompts, output_dir="output/text"):
    """
    Save the story and image prompts to a file.
    
    Args:
        story (str): The generated story
        prompt (str): The original prompt
        image_prompts (list): List of image prompts
        output_dir (str): Directory to save the file in
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(output_dir, f"story_{timestamp}.txt")
    
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(f"Prompt: {prompt}\n\n")
        f.write(f"Story:\n{story}\n\n")
        f.write("Image Prompts:\n")
        for idx, image_prompt in enumerate(image_prompts, start=1):
            f.write(f"{idx}: {image_prompt}\n")
    
    logging.info(f"Story and image prompts saved to: {file_path}")
    return file_path

def save_story(story):
    file_path = f"story_{timestamp}.txt"
    with open(file_path, "w") as f:
        f.write(story)
    return file_path  # Return the file path where the story is saved

