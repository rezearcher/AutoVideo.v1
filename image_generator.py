import logging
import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from openai import OpenAI

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
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        )
    return client


def search_pexels_image(query, output_path):
    """
    Search for a stock image on Pexels and download it.

    Args:
        query (str): Search query for the image
        output_path (str): Path where the image should be saved

    Returns:
        str: Path to the saved image
    """
    try:
        api_key = os.getenv("PEXELS_API_KEY")
        if not api_key:
            raise ValueError("PEXELS_API_KEY environment variable is not set")

        # Clean up the query - extract key words from the prompt
        # Remove common prompt words and focus on the main subject
        query_words = (
            query.lower()
            .replace("image of", "")
            .replace("photo of", "")
            .replace("picture of", "")
        )
        query_words = (
            query_words.replace("a ", "").replace("an ", "").replace("the ", "")
        )
        # Take first few meaningful words
        clean_query = " ".join(query_words.split()[:3])

        logging.info(
            f"Searching Pexels for: '{clean_query}' (from prompt: '{query[:50]}...')"
        )

        # Search Pexels API
        headers = {"Authorization": api_key}

        params = {
            "query": clean_query,
            "per_page": 5,  # Get a few options
            "orientation": "landscape",  # Better for video
        }

        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("photos") or len(data["photos"]) == 0:
            raise ValueError(f"No images found on Pexels for query: {clean_query}")

        # Get the first image (highest quality)
        photo = data["photos"][0]
        image_url = photo["src"]["large"]  # Use large size for good quality

        logging.info(f"Found Pexels image: {image_url}")

        # Download the image
        image_response = requests.get(image_url, timeout=30)
        image_response.raise_for_status()

        # Save the image
        with open(output_path, "wb") as f:
            f.write(image_response.content)

        logging.info(f"Downloaded Pexels image to: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Error searching Pexels: {str(e)}")
        raise


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
        logging.info(
            f"API Key: {os.getenv('OPENAI_API_KEY')[:5]}...{os.getenv('OPENAI_API_KEY')[-5:]}"
        )
        logging.info(
            f"Organization ID: {os.getenv('OPENAI_ORG_ID')[:5]}...{os.getenv('OPENAI_ORG_ID')[-5:]}"
        )

        # Make the API call
        logging.info(f"Making OpenAI API call for prompt: {prompt[:100]}...")
        response = client.images.generate(prompt=prompt, n=1, size="1024x1024")

        logging.info(f"OpenAI API response type: {type(response)}")
        logging.info(f"OpenAI API response: {response}")

        # Validate the response
        if response is None:
            raise ValueError("OpenAI API returned None response")

        if not hasattr(response, "data") or not response.data:
            raise ValueError("OpenAI API response has no data")

        if len(response.data) == 0:
            raise ValueError("OpenAI API response data is empty")

        if not hasattr(response.data[0], "url") or not response.data[0].url:
            raise ValueError("OpenAI API response has no image URL")

        image_url = response.data[0].url
        logging.info(f"Generated image URL: {image_url}")

        # Download the image
        image_response = requests.get(image_url)
        image_response.raise_for_status()

        # Save the image
        with open(output_path, "wb") as f:
            f.write(image_response.content)

        logging.info(f"Generated and saved image to: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Error generating image: {str(e)}")
        logging.error(f"Exception type: {type(e)}")
        logging.error(f"Exception details: {repr(e)}")
        raise


def generate_images(prompts, output_dir):
    """
    Generate multiple images from a list of prompts with fallback strategy.

    Strategy:
    1. Try OpenAI DALL-E first (best quality)
    2. Fall back to Pexels stock images if OpenAI fails

    Args:
        prompts (list): List of image prompts
        output_dir (str): Directory to save the images in

    Returns:
        list: List of paths to the generated images
    """
    os.makedirs(output_dir, exist_ok=True)
    image_paths = []

    logging.info(f"Generating {len(prompts)} images with fallback strategy...")

    for idx, prompt in enumerate(prompts, start=1):
        output_path = os.path.join(output_dir, f"image_{idx}.png")
        image_generated = False

        # Strategy 1: Try OpenAI DALL-E first
        try:
            logging.info(
                f"🎨 Attempting OpenAI DALL-E for image {idx}/{len(prompts)}: {prompt[:50]}..."
            )
            image_path = generate_image(prompt, output_path)
            image_paths.append(image_path)
            logging.info(f"✅ OpenAI DALL-E success for image {idx}/{len(prompts)}")
            image_generated = True
        except Exception as openai_error:
            logging.warning(
                f"⚠️ OpenAI DALL-E failed for image {idx}/{len(prompts)}: {str(openai_error)}"
            )

            # Strategy 2: Fall back to Pexels stock images
            try:
                logging.info(
                    f"🔄 Falling back to Pexels for image {idx}/{len(prompts)}: {prompt[:50]}..."
                )
                image_path = search_pexels_image(prompt, output_path)
                image_paths.append(image_path)
                logging.info(
                    f"✅ Pexels fallback success for image {idx}/{len(prompts)}"
                )
                image_generated = True
            except Exception as pexels_error:
                logging.error(
                    f"❌ Both OpenAI and Pexels failed for image {idx}/{len(prompts)}"
                )
                logging.error(f"   OpenAI error: {str(openai_error)}")
                logging.error(f"   Pexels error: {str(pexels_error)}")
                # Continue to next image instead of failing completely
                continue

        if image_generated:
            logging.info(f"✅ Successfully generated image {idx}/{len(prompts)}")

    if len(image_paths) == 0:
        logging.error(
            f"❌ Failed to generate any images out of {len(prompts)} attempts"
        )
        raise Exception(
            f"Failed to generate any images. All {len(prompts)} image generation attempts failed with both OpenAI and Pexels."
        )

    success_rate = len(image_paths) / len(prompts) * 100
    logging.info(
        f"✅ Successfully generated {len(image_paths)}/{len(prompts)} images ({success_rate:.1f}% success rate)"
    )
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
