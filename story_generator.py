import openai
import os
from dotenv import load_dotenv
from datetime import datetime
import time
import sys
import logging

# Load environment variables
load_dotenv()

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
            openai.api_key = os.getenv("OPENAI_API_KEY")
            openai.organization = os.getenv("OPENAI_ORG_ID")
            
            if not openai.api_key:
                raise ValueError("OpenAI API key not found in environment variables")
            
            logging.info("Sending request to OpenAI API...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a creative storyteller. Create engaging, detailed stories that are 3-5 paragraphs long. Each paragraph should be rich in visual details."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7,
            )
            
            story = response.choices[0].message.content.strip()
            logging.info("Story generated successfully")
            logging.debug(f"Generated story: {story}")
            
            return story, prompt
            
        except openai.error.AuthenticationError as e:
            logging.error(f"OpenAI authentication error: {str(e)}")
            raise
        except openai.error.RateLimitError as e:
            logging.warning(f"OpenAI rate limit hit, retrying... ({retry_count + 1}/{max_retries})")
            retry_count += 1
            time.sleep(2 ** retry_count)  # Exponential backoff
        except Exception as e:
            logging.error(f"Error generating story: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed to generate story after {max_retries} attempts: {str(e)}")
            time.sleep(1)

def extract_image_prompts(story):
    """
    Extract image prompts from the story.
    
    Args:
        story (str): The story text
        
    Returns:
        list: List of image prompts
    """
    logging.info("Extracting image prompts from story")
    
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        openai.organization = os.getenv("OPENAI_ORG_ID")
        
        if not openai.api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        
        logging.info("Sending request to OpenAI API for image prompts...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a creative image prompt generator. Extract 3-5 key scenes from the story that would make good images. Each prompt should be detailed and descriptive, focusing on visual elements, lighting, mood, and composition."},
                {"role": "user", "content": f"Extract image prompts from this story:\n\n{story}"}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        
        prompts = response.choices[0].message.content.strip().split('\n')
        prompts = [p.strip() for p in prompts if p.strip()]
        
        logging.info(f"Successfully extracted {len(prompts)} image prompts")
        logging.debug(f"Image prompts: {prompts}")
        
        return prompts
        
    except openai.error.AuthenticationError as e:
        logging.error(f"OpenAI authentication error: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Error extracting image prompts: {str(e)}")
        raise

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

