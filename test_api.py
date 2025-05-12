import os
import sys
import logging
from dotenv import load_dotenv
import openai
from elevenlabs import generate, set_api_key
import google.oauth2.credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_openai():
    """Test OpenAI API connection"""
    try:
        client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
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
        # YouTube API setup
        SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
        credentials = None
        
        # Check if we have valid credentials
        if os.path.exists('token.json'):
            credentials = google.oauth2.credentials.Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # If no valid credentials available, let the user log in
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', SCOPES)
                credentials = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(credentials.to_json())
        
        # Build the YouTube service
        youtube = build('youtube', 'v3', credentials=credentials)
        
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