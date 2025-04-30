import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key
api_key = os.getenv("OPENAI_API_KEY")
print(f"API Key loaded: {'Yes' if api_key else 'No'}")
if api_key:
    print(f"Key starts with: {api_key[:8]}...")  # Show first 8 chars safely

# Set API key
openai.api_key = api_key

try:
    # Make a simple API call
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello!"}
        ],
        max_tokens=10
    )
    print("API call successful!")
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print("Error:", str(e)) 