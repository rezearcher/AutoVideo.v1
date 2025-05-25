from openai import OpenAI
import os
import logging

# Initialize OpenAI client globally
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def extract_image_prompts(story, num_prompts=5):
    """
    Extract image prompts from a story.
    
    Args:
        story (str): The story to extract prompts from
        num_prompts (int): Number of prompts to generate
        
    Returns:
        list: List of image prompts
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting image prompts from story...")
    
    # Split story into sentences and create concise prompts
    sentences = story.split('.')
    prompts = []
    
    for sentence in sentences:
        if len(prompts) >= num_prompts:
            break
        # Clean up the sentence and take first 10 words
        words = sentence.strip().split()[:10]
        if len(words) > 3:  # Only use meaningful sentences
            prompt = ' '.join(words) + ' photorealistic'
            prompts.append(prompt)
    
    # If we don't have enough prompts, duplicate the last one
    while len(prompts) < num_prompts:
        prompts.append(prompts[-1])
    
    logger.info(f"Generated {len(prompts)} image prompts")
    return prompts[:num_prompts]
