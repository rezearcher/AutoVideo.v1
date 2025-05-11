import openai  # Using openai package version 0.28.0
import os
import requests
from datetime import datetime
import time
import logging
from dotenv import load_dotenv

load_dotenv()
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_images(prompts, output_dir):
    """
    Generate images from a list of prompts and save them to the specified directory.
    
    Args:
        prompts (list): List of image prompts
        output_dir (str): Directory where the images should be saved
        
    Returns:
        list: List of paths to the saved images
    """
    try:
        image_paths = []
        for prompt in prompts:
            output_path = os.path.join(output_dir, f"image_{len(image_paths)}.png")
            image_path = generate_image(prompt, output_path)
            image_paths.append(image_path)
        return image_paths
    except Exception as e:
        logging.error(f"Error generating images: {str(e)}")
        raise

def generate_image(prompt, output_path):
    """
    Generate an image from a prompt and save it to the specified path.
    
    Args:
        prompt (str): The image prompt
        output_path (str): Path where the image should be saved
        
    Returns:
        str: Path to the saved image
    """
    try:
        # Ensure the output directory exists
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"Ensuring output directory exists: {output_dir}")
        
        logging.info(f"Generating image for prompt: {prompt}")
        logging.info(f"Output path: {output_path}")
        
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="url"
        )

        if response.data:
            image_url = response.data[0].url
            logging.info(f"Image generated successfully, downloading from URL: {image_url}")
            
            # Download and save the image
            download_image(image_url, output_path)
            
            # Verify the image was saved
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"Failed to save image to {output_path}")
            if os.path.getsize(output_path) == 0:
                raise ValueError(f"Saved image is empty: {output_path}")
                
            logging.info(f"Image saved successfully to: {output_path}")
            return output_path
        else:
            logging.error(f"Error generating image for prompt '{prompt}': No data in response")
            return None
    except Exception as e:
        logging.error(f"Error generating image: {str(e)}")
        raise

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
