import openai
import os
from dotenv import load_dotenv
from datetime import datetime
import time
import sys
import logging

load_dotenv()
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

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
    
    while retry_count < max_retries:
        if time.time() - start_time > timeout:
            raise Exception("Story generation timed out")
            
        try:
            openai.api_key = os.getenv("OPENAI_API_KEY")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a creative storyteller. Create engaging, detailed stories that are 3-5 paragraphs long. Each paragraph should be rich in visual details."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,  # Increased from 300
                temperature=0.7,
            )
            story = response.choices[0].message.content.strip()
            print("\nGenerated Story:")
            print(story)
            
            # Automatically proceed with 'y'
            return story, prompt
            
        except Exception as e:
            logging.error(f"Error generating story: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed to generate story after {max_retries} attempts")
            time.sleep(1)  # Brief pause before retry

def extract_image_prompts(story):
    """
    Extract image prompts from the story.
    
    Args:
        story (str): The story text
        
    Returns:
        list: List of image prompts
    """
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a creative image prompt generator. Extract 3-5 key scenes from the story that would make good images. Each prompt should be detailed and descriptive, focusing on visual elements, lighting, mood, and composition."},
                {"role": "user", "content": f"Extract image prompts from this story:\n\n{story}"}
            ],
            max_tokens=500,  # Increased from 200
            temperature=0.7,
        )
        prompts = response.choices[0].message.content.strip().split('\n')
        return [p.strip() for p in prompts if p.strip()]
    except Exception as e:
        logging.error(f"Error extracting image prompts: {str(e)}")
        raise

def save_story_with_image_prompts(story, prompt, image_prompts):
    with open(f"story_{timestamp}.txt", "w") as f:
        f.write(prompt + "\n" + story + "\n\nImage Prompts:\n")
        for idx, image_prompt in enumerate(image_prompts, start=1):
            f.write(f"{idx}: {image_prompt}\n")

def save_story(story):
    file_path = f"story_{timestamp}.txt"
    with open(file_path, "w") as f:
        f.write(story)
    return file_path  # Return the file path where the story is saved

