import os
import openai


def test_openai_connectivity():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("FAIL: OPENAI_API_KEY environment variable is not set.")
        return False
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OpenAI API is working!'"},
            ],
            max_tokens=10,
        )
        print("SUCCESS: OpenAI API is working!")
        print("Response:", response.choices[0].message.content)
        return True
    except Exception as e:
        print(f"FAIL: OpenAI API test failed - {e}")
        return False


if __name__ == "__main__":
    test_openai_connectivity()
