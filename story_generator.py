import os
import logging
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import time
import random

# Load environment variables
load_dotenv()

# Global client variable for lazy initialization
client = None

def get_openai_client():
    """Get or initialize the OpenAI client."""
    global client
    if client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        client = OpenAI(
            api_key=api_key,
            organization=os.getenv('OPENAI_ORG_ID'),
            base_url=os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1'),
            timeout=30.0  # 30 second timeout per request
        )
    return client

def call_openai_with_backoff(max_retries=3, max_time=60, **kwargs):
    """
    Call OpenAI API with exponential backoff and jitter.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        max_time (int): Maximum total time to spend retrying
        **kwargs: Arguments to pass to the OpenAI API call
        
    Returns:
        OpenAI response object
    """
    start_time = time.time()
    
    for attempt in range(max_retries):
        # Check if we've exceeded the total time limit
        if time.time() - start_time > max_time:
            raise Exception(f"OpenAI API call timed out after {max_time} seconds")
        
        try:
            client = get_openai_client()
            logging.info(f"OpenAI API call attempt {attempt + 1}/{max_retries}")
            
            response = client.chat.completions.create(**kwargs)
            logging.info(f"OpenAI API call successful on attempt {attempt + 1}")
            return response
            
        except Exception as e:
            logging.warning(f"OpenAI API call attempt {attempt + 1} failed: {str(e)}")
            
            # Don't retry on the last attempt
            if attempt == max_retries - 1:
                raise Exception(f"OpenAI API failed after {max_retries} attempts: {str(e)}")
            
            # Calculate exponential backoff with jitter
            base_delay = 2 ** attempt  # 1, 2, 4 seconds
            jitter = random.uniform(0, 1)  # Add randomness to avoid thundering herd
            delay = base_delay + jitter
            
            # Don't delay if we're close to the time limit
            remaining_time = max_time - (time.time() - start_time)
            if remaining_time <= delay:
                logging.warning(f"Skipping delay due to time limit (remaining: {remaining_time:.1f}s)")
                continue
                
            logging.info(f"Retrying in {delay:.1f} seconds...")
            time.sleep(delay)
    
    raise Exception(f"OpenAI API failed after {max_retries} attempts")


def generate_story(prompt, timeout=90):
    """
    Generate a story from a prompt with enhanced retry logic.
    
    Args:
        prompt (str): The story prompt
        timeout (int): Maximum time in seconds to wait for story generation
        
    Returns:
        tuple: (story, prompt)
    """
    logging.info(f"Starting story generation with prompt: {prompt}")
    logging.info(f"Story generation timeout set to {timeout} seconds")
    
    try:
        response = call_openai_with_backoff(
            max_retries=3,
            max_time=timeout,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a creative storyteller. Write engaging, vivid stories suitable for video content."},
                {"role": "user", "content": f"Write a compelling short story about: {prompt}. Make it visual and engaging for video content."}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        story = response.choices[0].message.content.strip()
        logging.info(f"Successfully generated story (length: {len(story)} characters)")
        return story, prompt
        
    except Exception as e:
        logging.error(f"Story generation failed: {str(e)}")
        raise Exception(f"Story generation timed out")


def extract_image_prompts(story, num_scenes=5, timeout=60):
    """Extract image prompts from the story with enhanced retry logic."""
    try:
        logging.info(f"Extracting {num_scenes} image prompts from story...")
        
        prompt = f"""
        Given this story, create exactly {num_scenes} detailed image prompts that capture key scenes.
        Make each prompt detailed and descriptive for AI image generation.
        Format as a numbered list.
        
        Story: {story}
        """
        
        response = call_openai_with_backoff(
            max_retries=3,
            max_time=timeout,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at creating detailed image prompts from stories. Create vivid, specific prompts perfect for AI image generation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        prompts_text = response.choices[0].message.content.strip()
        prompts = [p.strip() for p in prompts_text.split('\n') if p.strip() and not p.strip().isdigit()]
        
        # Clean up prompts (remove numbering if present)
        cleaned_prompts = []
        for p in prompts:
            # Remove leading numbers and punctuation
            cleaned = p.lstrip('0123456789. -')
            if cleaned and len(cleaned) > 10:  # Ensure it's a real prompt
                cleaned_prompts.append(cleaned)
        
        logging.info(f"Generated {len(cleaned_prompts)} image prompts")
        return cleaned_prompts[:num_scenes]
        
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

