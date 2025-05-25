import os
import sys
import requests
from openai import OpenAI
from elevenlabs import generate, set_api_key

def test_openai():
    try:
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY')
        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        print("✅ OpenAI API test passed")
        return True
    except Exception as e:
        print(f"❌ OpenAI API test failed: {str(e)}")
        return False

def test_elevenlabs():
    try:
        set_api_key(os.getenv('ELEVENLABS_API_KEY'))
        audio = generate(
            text="Hello, this is a test.",
            voice="Bella",
            model="eleven_monolingual_v1"
        )
        print("✅ ElevenLabs API test passed")
        return True
    except Exception as e:
        print(f"❌ ElevenLabs API test failed: {str(e)}")
        return False

def test_youtube():
    try:
        # Basic YouTube API test
        client_id = os.getenv('YOUTUBE_CLIENT_ID')
        client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
        project_id = os.getenv('YOUTUBE_PROJECT_ID')
        
        if not all([client_id, client_secret, project_id]):
            print("❌ YouTube API credentials missing")
            return False
            
        print("✅ YouTube API credentials present")
        return True
    except Exception as e:
        print(f"❌ YouTube API test failed: {str(e)}")
        return False

def main():
    print("Starting API connectivity tests...")
    
    tests = [
        ("OpenAI", test_openai),
        ("ElevenLabs", test_elevenlabs),
        ("YouTube", test_youtube)
    ]
    
    all_passed = True
    for name, test_func in tests:
        print(f"\nTesting {name} API...")
        if not test_func():
            all_passed = False
    
    if all_passed:
        print("\n✅ All API tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some API tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 