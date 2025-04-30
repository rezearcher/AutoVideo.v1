import requests
import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

def generate_voiceover(story, output_path):
    """
    Generate a voiceover for the story and save it to the specified path.
    
    Args:
        story (str): The story text to convert to speech
        output_path (str): Path where the voiceover should be saved
        
    Returns:
        str: Path to the saved voiceover file
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("\nError: ELEVENLABS_API_KEY environment variable is not set!")
        print("Please set your ElevenLabs API key in the .env file or environment variables.")
        print("You can get an API key from: https://elevenlabs.io")
        raise ValueError("ELEVENLABS_API_KEY environment variable is not set")

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "accept": "audio/mpeg"
    }
    
    data = {
        "text": story,
        "voice_settings": {"stability": 0.3, "similarity_boost": 0.3}
    }

    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds

    while retry_count < max_retries:
        try:
            print("\nGenerating voiceover...")
            response = requests.post(
                "https://api.elevenlabs.io/v1/text-to-speech/AZnzlk1XvdvUeBnXmlld",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                # Create the directory if it doesn't exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Save the voiceover file
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                # Verify the file was created and has content
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    print(f"Voiceover saved successfully to: {output_path}")
                    return output_path
                else:
                    raise Exception("Voiceover file was not created or is empty")
            else:
                error_msg = f"Error while generating voiceover with status code {response.status_code}"
                try:
                    error_details = response.json()
                    error_msg += f": {error_details}"
                except:
                    error_msg += f": {response.text}"
                print(f"\nError: {error_msg}")
                raise Exception(error_msg)
                
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"\nError: Failed to generate voiceover after {max_retries} attempts: {str(e)}")
                raise
            print(f"\nRetrying ({retry_count}/{max_retries})...")
            time.sleep(retry_delay * retry_count)  # Exponential backoff

def save_voiceover(voiceover_content, timestamp):
    """Save voiceover content to a file."""
    try:
        voiceover_filename = f"voiceover_{timestamp}.mp3"
        with open(voiceover_filename, "wb") as f:
            f.write(voiceover_content)
        print(f"Voiceover saved to: {voiceover_filename}")
        return voiceover_filename
    except Exception as e:
        print(f"Error saving voiceover: {str(e)}")
        raise
