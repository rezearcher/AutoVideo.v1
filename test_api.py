import os
import sys
import logging
from dotenv import load_dotenv
import openai
from elevenlabs import generate, set_api_key
from youtube_uploader.token_manager import TokenManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_openai():
    """Test OpenAI API connection"""
    try:
        # Initialize OpenAI client without proxies
        client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1"
        )
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OpenAI API is working!'"}
            ],
            max_tokens=50
        )
        logger.info("OpenAI API Test: SUCCESS")
        logger.info(f"Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        logger.error(f"OpenAI API Test: FAILED - {str(e)}")
        return False

def test_elevenlabs():
    """Test ElevenLabs API connection"""
    try:
        set_api_key(os.getenv("ELEVENLABS_API_KEY"))
        audio = generate(
            text="ElevenLabs API is working!",
            voice="Bella",
            model="eleven_monolingual_v1"
        )
        logger.info("ElevenLabs API Test: SUCCESS")
        return True
    except Exception as e:
        logger.error(f"ElevenLabs API Test: FAILED - {str(e)}")
        return False

def test_youtube():
    """Test YouTube API connection"""
    try:
        # Skip YouTube test if not enabled
        if not os.getenv("YOUTUBE_ENABLED", "false").lower() == "true":
            logger.info("YouTube API Test: SKIPPED (not enabled)")
            return True

        # Initialize token manager
        token_manager = TokenManager()
        
        # Get YouTube service
        youtube = token_manager.get_youtube_service()
        
        # Test the connection by getting channel info
        request = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            mine=True
        )
        response = request.execute()
        
        logger.info("YouTube API Test: SUCCESS")
        logger.info(f"Channel Title: {response['items'][0]['snippet']['title']}")
        return True
    except Exception as e:
        logger.error(f"YouTube API Test: FAILED - {str(e)}")
        return False

def main():
    """Run all API tests"""
    load_dotenv()
    
    logger.info("Starting API tests...")
    
    # Test OpenAI
    openai_success = test_openai()
    
    # Test ElevenLabs
    elevenlabs_success = test_elevenlabs()
    
    # Test YouTube
    youtube_success = test_youtube()
    
    # Print summary
    logger.info("\nTest Summary:")
    logger.info(f"OpenAI API: {'✓' if openai_success else '✗'}")
    logger.info(f"ElevenLabs API: {'✓' if elevenlabs_success else '✗'}")
    logger.info(f"YouTube API: {'✓' if youtube_success else '✗'}")
    
    if all([openai_success, elevenlabs_success, youtube_success]):
        logger.info("\nAll API tests passed! You can now run the main application.")
    else:
        logger.error("\nSome API tests failed. Please check the errors above and fix them before running the main application.")

if __name__ == "__main__":
    main() 