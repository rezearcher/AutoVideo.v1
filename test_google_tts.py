#!/usr/bin/env python3
"""
Simple test script for Google Cloud Text-to-Speech API.
This helps verify that the API is enabled and working.
"""

import os
import tempfile

from google.cloud import texttospeech

# Set up a test message
test_text = "This is a test of the Google Cloud Text-to-Speech API. If you can hear this message, it means the API is working correctly."


def test_google_tts():
    """Test Google Cloud Text-to-Speech directly."""
    print("🧪 Testing Google Cloud Text-to-Speech...")

    # Create a temporary file to store the output
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        # Initialize the client
        client = texttospeech.TextToSpeechClient()
        print("✅ Successfully initialized TextToSpeechClient")

        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=test_text)

        # Build the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Studio-O",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        # Select the type of audio file
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
        )

        # List available voices to verify API connection
        try:
            voices = client.list_voices()
            print(f"✅ Successfully listed {len(voices.voices)} available voices")
        except Exception as e:
            print(f"❌ Failed to list voices: {str(e)}")
            raise

        # Perform the text-to-speech request
        print("🔄 Generating speech...")
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        # Save the audio content to the output file
        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        # Verify the file was created and has content
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            print(f"✅ Google TTS test successful! File saved: {output_path}")
            print(f"📊 File size: {file_size} bytes")

            # Play the audio file if on Linux
            print("\n🔊 Playing the audio file...")
            os.system(
                f"play {output_path} || aplay {output_path} || echo 'Could not play audio'"
            )

            return True
        else:
            print("❌ Google TTS test failed: File not created or empty")
            return False

    except Exception as e:
        print(f"❌ Google TTS test failed with error: {str(e)}")
        if "disabled" in str(e).lower():
            print("\n💡 The Text-to-Speech API might not be enabled. Enable it at:")
            print(
                "https://console.cloud.google.com/apis/library/texttospeech.googleapis.com"
            )
        elif "permission" in str(e).lower() or "credential" in str(e).lower():
            print("\n💡 There might be an issue with credentials. Try:")
            print("gcloud auth application-default login")
        return False
    finally:
        # Don't delete the file so user can check it
        print(f"\n💾 The output file is saved at: {output_path}")


if __name__ == "__main__":
    print("🚀 Starting Google Cloud TTS Test")
    result = test_google_tts()
    print("\n📋 Test Result:", "✅ PASSED" if result else "❌ FAILED")
