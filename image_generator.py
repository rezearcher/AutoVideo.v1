from openai import OpenAI
import os
import requests
from datetime import datetime
import time
import logging
from dotenv import load_dotenv

load_dotenv()
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

# Global client variable for lazy initialization
client = None

def get_openai_client():
    """Get or initialize the OpenAI client."""
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        client = OpenAI(
            api_key=api_key,
            organization=os.getenv("OPENAI_ORG_ID"),
            base_url=os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        )
    return client

def generate_image(prompt, output_path):
    """
    Generate a single image from a prompt and save it to the specified path.
    
    Args:
        prompt (str): The image prompt
        output_path (str): Path where the image should be saved
        
    Returns:
        str: Path to the saved image
    """
    try:
        client = get_openai_client()
        logging.info(f"API Key: {os.getenv('OPENAI_API_KEY')[:5]}...{os.getenv('OPENAI_API_KEY')[-5:]}")
        logging.info(f"Organization ID: {os.getenv('OPENAI_ORG_ID')[:5]}...{os.getenv('OPENAI_ORG_ID')[-5:]}")
        response = client.images.generate(
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        
        image_url = response.data[0].url
        
        # Download the image
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        
        # Save the image
        with open(output_path, 'wb') as f:
            f.write(image_response.content)
            
        logging.info(f"Generated and saved image to: {output_path}")
        return output_path
        
    except Exception as e:
        logging.error(f"Error generating image: {str(e)}")
        raise

def generate_images(prompts, output_dir):
    """
    Generate multiple images from a list of prompts.
    
    Args:
        prompts (list): List of image prompts
        output_dir (str): Directory to save the images in
        
    Returns:
        list: List of paths to the generated images
    """
    os.makedirs(output_dir, exist_ok=True)
    image_paths = []
    
    for idx, prompt in enumerate(prompts, start=1):
        output_path = os.path.join(output_dir, f"image_{idx}.png")
        try:
            image_path = generate_image(prompt, output_path)
            image_paths.append(image_path)
        except Exception as e:
            logging.error(f"Failed to generate image {idx}: {str(e)}")
            continue
            
    return image_paths

def download_image(url, filename):
    """Download an image from a URL and save it to a file."""
    try:
        logging.info(f"Downloading image from {url}")
        logging.info(f"Saving to: {filename}")
        
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, "wb") as f:
            f.write(response.content)
            
        # Verify the file was saved
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Failed to save image to {filename}")
        if os.path.getsize(filename) == 0:
            raise ValueError(f"Saved image is empty: {filename}")
            
        logging.info(f"Image downloaded and saved to {filename}")
        return filename
    except Exception as e:
        logging.error(f"Error downloading image: {str(e)}")
        raise
