import logging
import os
import time
from typing import Optional

import google.auth
import requests
from dotenv import load_dotenv
from google.cloud import texttospeech

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class VoiceoverError(Exception):
    """Base exception for voiceover generation errors"""

    pass


class ElevenLabsQuotaError(VoiceoverError):
    """Raised when ElevenLabs quota is exceeded"""

    pass


class ElevenLabsAPIError(VoiceoverError):
    """Raised when ElevenLabs API encounters an error"""

    pass


def generate_google_tts(
    text: str, output_path: str, voice_name: str = "en-US-Studio-O"
) -> str:
    """
    Generate voiceover using Google Cloud Text-to-Speech API.

    Args:
        text (str): The text to convert to speech
        output_path (str): Path where the voiceover should be saved
        voice_name (str): Voice name to use (default: "en-US-Studio-O")

    Returns:
        str: Path to the saved voiceover file

    Raises:
        VoiceoverError: If an error occurs during TTS generation
    """
    try:
        # Log attempt
        logger.info("🔄 Generating voiceover using Google Cloud TTS...")

        # Import here to avoid issues with circular imports
        import os

        # Check if credentials are properly set up
        try:
            # Get default credentials and project
            credentials, project_id = google.auth.default()
            logger.info(
                f"🔑 Using Google Cloud service account: {getattr(credentials, 'service_account_email', 'Unknown')}"
            )
            logger.info(f"🔑 Project ID: {project_id}")
        except Exception as cred_error:
            logger.warning(f"⚠️ Default credentials not found: {cred_error}")
            # Check if credentials file is explicitly set
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path:
                logger.info(f"🔑 Using explicit credentials file: {creds_path}")
                if not os.path.exists(creds_path):
                    logger.error(f"❌ Credentials file does not exist: {creds_path}")
            else:
                logger.warning(
                    "⚠️ GOOGLE_APPLICATION_CREDENTIALS environment variable not set"
                )

        # Create the Text-to-Speech client
        client = texttospeech.TextToSpeechClient()

        # Log successful client creation
        logger.info("✅ TextToSpeechClient created successfully")

        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Build the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )

        # Select the type of audio file
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
        )

        # Log TTS request
        logger.info(f"🔊 Sending TTS request for {len(text)} characters of text")

        # Perform the text-to-speech request
        try:
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            logger.info(
                f"✅ TTS request successful, received {len(response.audio_content)} bytes of audio"
            )
        except Exception as api_error:
            error_msg = str(api_error)
            if "permission" in error_msg.lower() or "credential" in error_msg.lower():
                logger.error(
                    f"❌ Google TTS permission/authentication error: {error_msg}"
                )
                raise VoiceoverError(f"Google TTS authentication error: {error_msg}")
            else:
                logger.error(f"❌ Google TTS API error: {error_msg}")
                raise VoiceoverError(f"Google TTS API error: {error_msg}")

        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save the audio content to the output file
        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        # Verify the file was created and has content
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"✅ Google TTS voiceover saved successfully to: {output_path}")
            return output_path
        else:
            raise VoiceoverError(
                "Google TTS voiceover file was not created or is empty"
            )

    except Exception as e:
        logger.error(f"❌ Google Cloud TTS failed: {str(e)}")
        raise VoiceoverError(f"Google Cloud TTS generation failed: {str(e)}")


def generate_elevenlabs_tts(text: str, output_path: str) -> str:
    """
    Generate voiceover using ElevenLabs API.

    Args:
        text (str): The text to convert to speech
        output_path (str): Path where the voiceover should be saved

    Returns:
        str: Path to the saved voiceover file

    Raises:
        ElevenLabsQuotaError: If quota is exceeded
        ElevenLabsAPIError: If API encounters other errors
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ElevenLabsAPIError("ELEVENLABS_API_KEY environment variable is not set")

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "accept": "audio/mpeg",
    }

    data = {
        "text": text,
        "voice_settings": {"stability": 0.3, "similarity_boost": 0.3},
    }

    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds

    while retry_count < max_retries:
        try:
            logger.info("🔄 Generating voiceover using ElevenLabs...")
            response = requests.post(
                "https://api.elevenlabs.io/v1/text-to-speech/AZnzlk1XvdvUeBnXmlld",
                headers=headers,
                json=data,
                timeout=30,  # Add timeout
            )

            if response.status_code == 200:
                # Create the directory if it doesn't exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Save the voiceover file
                with open(output_path, "wb") as f:
                    f.write(response.content)

                # Verify the file was created and has content
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(
                        f"✅ ElevenLabs voiceover saved successfully to: {output_path}"
                    )
                    return output_path
                else:
                    raise ElevenLabsAPIError(
                        "ElevenLabs voiceover file was not created or is empty"
                    )

            elif response.status_code == 429:  # Rate limit exceeded
                raise ElevenLabsQuotaError("ElevenLabs rate limit exceeded")
            elif response.status_code in [
                402,
                403,
            ]:  # Payment required or forbidden (quota)
                raise ElevenLabsQuotaError(
                    "ElevenLabs quota exceeded or payment required"
                )
            else:
                error_msg = f"ElevenLabs API error {response.status_code}"
                try:
                    error_details = response.json()
                    error_msg += f": {error_details}"

                    # Check for quota-related messages in the response
                    error_text = str(error_details).lower()
                    if any(
                        keyword in error_text
                        for keyword in ["quota", "limit", "exceeded", "insufficient"]
                    ):
                        raise ElevenLabsQuotaError(
                            f"ElevenLabs quota issue: {error_details}"
                        )

                except:
                    error_msg += f": {response.text}"

                raise ElevenLabsAPIError(error_msg)

        except ElevenLabsQuotaError:
            # Don't retry quota errors, let them bubble up immediately
            raise
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                if "timeout" in str(e).lower():
                    raise ElevenLabsAPIError(
                        f"ElevenLabs API timeout after {max_retries} attempts"
                    )
                else:
                    raise ElevenLabsAPIError(
                        f"ElevenLabs API failed after {max_retries} attempts: {str(e)}"
                    )

            logger.warning(
                f"⚠️ ElevenLabs attempt {retry_count} failed, retrying in {retry_delay * retry_count}s..."
            )
            time.sleep(retry_delay * retry_count)  # Exponential backoff


def generate_voiceover(
    story: str, output_path: str, tts_service: str = "elevenlabs"
) -> str:
    """
    Generate a voiceover for the story with automatic fallback from ElevenLabs to Google Cloud TTS.

    Args:
        story (str): The story text to convert to speech
        output_path (str): Path where the voiceover should be saved
        tts_service (str): TTS service to use: "elevenlabs" (default with fallback) or "google"

    Returns:
        str: Path to the saved voiceover file

    Raises:
        VoiceoverError: If both ElevenLabs and Google TTS fail
    """
    start_time = time.time()
    max_time = 300  # 5 minutes max for entire voiceover generation

    # Log which service we're using
    logger.info(f"🎙️ Voiceover generation requested with service: {tts_service}")

    # If Google TTS is explicitly requested, use it directly
    if tts_service.lower() == "google":
        logger.info("🔊 Using Google Cloud Text-to-Speech as requested...")
        try:
            logger.info("🔄 Starting Google TTS generation...")
            result = generate_google_tts(story, output_path)
            duration = time.time() - start_time
            logger.info(f"✅ Google TTS generation successful in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ Google TTS failed after {duration:.2f}s: {str(e)}")
            # Log the error details clearly for debugging
            logger.error(f"❌ Google TTS error details: {type(e).__name__}: {str(e)}")
            raise VoiceoverError(f"Google Cloud TTS generation failed: {str(e)}")

    # 1) Try ElevenLabs first
    try:
        logger.info("▶️ [Voiceover] Attempting ElevenLabs TTS...")
        start_elevenlabs = time.time()
        result = generate_elevenlabs_tts(story, output_path)
        duration = time.time() - start_elevenlabs
        logger.info(
            f"✅ [Voiceover] ElevenLabs generation successful in {duration:.2f}s"
        )
        return result  # Exit immediately on ElevenLabs success
    except ElevenLabsQuotaError as e:
        duration = time.time() - start_elevenlabs
        logger.warning(
            f"⚠️ [Voiceover] ElevenLabs quota exceeded after {duration:.2f}s: {str(e)}"
        )
        logger.info("▶️ [Voiceover] Attempting Google TTS fallback (quota exceeded)...")
    except ElevenLabsAPIError as e:
        # For other ElevenLabs errors, still try Google TTS but log differently
        duration = time.time() - start_elevenlabs
        logger.warning(
            f"⚠️ [Voiceover] ElevenLabs API error after {duration:.2f}s: {str(e)}"
        )
        logger.info("▶️ [Voiceover] Attempting Google TTS fallback (API error)...")
    except Exception as e:
        # Handle any other unexpected errors
        duration = time.time() - start_time
        logger.error(
            f"❌ [Voiceover] Unexpected error in voiceover generation after {duration:.2f}s: {str(e)}"
        )
        logger.error(f"❌ [Voiceover] Error type: {type(e).__name__}")
        logger.info(
            "▶️ [Voiceover] Attempting Google TTS fallback (unexpected error)..."
        )

    # Check if we're about to exceed the total time limit
    if time.time() - start_time > max_time:
        logger.error(f"❌ Voiceover generation timed out after {max_time}s")
        raise VoiceoverError(f"Voiceover generation timed out after {max_time}s")

    # 2) Try Google TTS (fallback)
    try:
        start_google = time.time()
        logger.info("▶️ [Voiceover] Starting Google TTS fallback...")
        result = generate_google_tts(story, output_path)
        duration = time.time() - start_google
        logger.info(f"✅ [Voiceover] Google TTS fallback successful in {duration:.2f}s")
        return result  # IMPORTANT: don't re-raise, just exit on success
    except Exception as fallback_error:
        duration = time.time() - start_google
        logger.error(
            f"❌ [Voiceover] Google TTS fallback failed after {duration:.2f}s: {str(fallback_error)}"
        )
        # Log error details clearly for debugging
        logger.error(
            f"❌ [Voiceover] Google TTS error: {type(fallback_error).__name__}: {str(fallback_error)}"
        )
        # Only raise if both ElevenLabs and Google TTS failed
        raise VoiceoverError(
            f"Both ElevenLabs and Google TTS failed. Google TTS: {str(fallback_error)}"
        )


def save_voiceover(voiceover_content, timestamp):
    """Save voiceover content to a file."""
    try:
        voiceover_filename = f"voiceover_{timestamp}.mp3"
        with open(voiceover_filename, "wb") as f:
            f.write(voiceover_content)
        logger.info(f"Voiceover saved to: {voiceover_filename}")
        return voiceover_filename
    except Exception as e:
        logger.error(f"Error saving voiceover: {str(e)}")
        raise
