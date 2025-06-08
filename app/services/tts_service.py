import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import elevenlabs
from elevenlabs.api import Error as ElevenLabsError
from google.cloud import texttospeech

from app.config import settings
from app.utils.audio_utils import normalize_audio_loudness

logger = logging.getLogger(__name__)

# Create cache directory for TTS outputs
VO_CACHE = Path("/tmp/vo_cache")
VO_CACHE.mkdir(parents=True, exist_ok=True)


class TTSService:
    """Service for text-to-speech processing."""

    def __init__(self):
        self._elevenlabs_api_key = settings.ELEVENLABS_API_KEY
        self._elevenlabs_available = bool(self._elevenlabs_api_key)
        self._google_tts_client = None

        if self._elevenlabs_available:
            elevenlabs.set_api_key(self._elevenlabs_api_key)
            logger.info("ElevenLabs TTS initialized")
        else:
            logger.info("ElevenLabs TTS not available - will use Google TTS")

    def _get_google_tts_client(self):
        """Get or create Google TTS client."""
        if self._google_tts_client is None:
            self._google_tts_client = texttospeech.TextToSpeechClient()
        return self._google_tts_client

    def generate_speech(
        self,
        text: str,
        voice: str = "Adam",
        language_code: str = "en-US",
        normalize: bool = True,
    ) -> str:
        """
        Generate speech from text using available TTS services.

        Args:
            text: Text to convert to speech
            voice: Voice to use (for ElevenLabs)
            language_code: Language code (for Google TTS)
            normalize: Whether to normalize audio loudness

        Returns:
            Path to the generated audio file
        """
        # Create hash for caching
        text_hash = hashlib.sha256(
            f"{text}_{voice}_{language_code}".encode()
        ).hexdigest()[:12]
        cache_path = VO_CACHE / f"{text_hash}.wav"

        # Check if cached version exists
        if cache_path.exists():
            logger.info(f"Using cached TTS audio for '{text[:30]}...'")
            return str(cache_path)

        # Try ElevenLabs first if available
        if self._elevenlabs_available:
            try:
                logger.info(f"Generating speech with ElevenLabs: '{text[:50]}...'")
                audio_data = self._generate_elevenlabs_speech(text, voice)

                # Save to temporary file
                with open(cache_path, "wb") as f:
                    f.write(audio_data)

                if normalize:
                    self._normalize_audio(cache_path)

                return str(cache_path)
            except Exception as e:
                logger.warning(
                    f"ElevenLabs TTS failed - falling back to Google TTS: {e}"
                )

        # Fall back to Google TTS
        try:
            logger.info(f"Generating speech with Google TTS: '{text[:50]}...'")
            audio_data = self._generate_google_speech(text, language_code)

            # Save to temporary file
            with open(cache_path, "wb") as f:
                f.write(audio_data)

            if normalize:
                self._normalize_audio(cache_path)

            return str(cache_path)
        except Exception as e:
            logger.error(f"Failed to generate speech: {e}")
            raise

    def _generate_elevenlabs_speech(self, text: str, voice: str) -> bytes:
        """Generate speech using ElevenLabs."""
        try:
            audio = elevenlabs.generate(
                text=text, voice=voice, model="eleven_monolingual_v1"
            )
            return audio
        except ElevenLabsError as e:
            if "quota" in str(e).lower():
                logger.warning("ElevenLabs quota exceeded - falling back to Google TTS")
            else:
                logger.error(f"ElevenLabs error: {e}")
            raise

    def _generate_google_speech(self, text: str, language_code: str) -> bytes:
        """Generate speech using Google TTS."""
        client = self._get_google_tts_client()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        return response.audio_content

    def _normalize_audio(self, audio_path: str) -> None:
        """Normalize audio loudness to broadcast standards."""
        try:
            normalize_audio_loudness(
                audio_path,
                audio_path,
                target_loudness=-16,
                true_peak=-1.5,
                loudness_range=11,
            )
            logger.info(f"Normalized audio loudness for {audio_path}")
        except Exception as e:
            logger.warning(f"Failed to normalize audio: {e}")
