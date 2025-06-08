"""Service for managing background music assets."""

import json
import logging
import os
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

import ffmpeg

from app.config import settings
from app.config.storage import get_gcs_uri, get_storage_path
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class MusicService:
    """Service for managing background music assets."""

    # Default music metadata
    DEFAULT_MUSIC = [
        {
            "filename": "upbeat_corporate.mp3",
            "title": "Upbeat Corporate",
            "mood": "positive",
            "tempo": "medium",
            "genre": "corporate",
            "duration": 60,
        },
        {
            "filename": "inspiring_technology.mp3",
            "title": "Inspiring Technology",
            "mood": "inspirational",
            "tempo": "medium",
            "genre": "technology",
            "duration": 65,
        },
        {
            "filename": "gentle_ambient.mp3",
            "title": "Gentle Ambient",
            "mood": "calm",
            "tempo": "slow",
            "genre": "ambient",
            "duration": 90,
        },
        {
            "filename": "energetic_dance.mp3",
            "title": "Energetic Dance",
            "mood": "energetic",
            "tempo": "fast",
            "genre": "electronic",
            "duration": 55,
        },
        {
            "filename": "cinematic_emotional.mp3",
            "title": "Cinematic Emotional",
            "mood": "emotional",
            "tempo": "slow",
            "genre": "cinematic",
            "duration": 75,
        },
    ]

    def __init__(self, storage_service: StorageService):
        self._storage_service = storage_service
        self._music_catalog = None
        self._catalog_loaded = False

    def _load_catalog(self) -> List[Dict[str, Any]]:
        """
        Load the music catalog from storage or use default.

        Returns:
            List of music metadata dictionaries
        """
        if self._catalog_loaded:
            return self._music_catalog

        try:
            # Try to load catalog file from storage
            catalog_path = get_storage_path("audio", "music", "catalog.json")
            local_path = f"/tmp/music_catalog_{uuid.uuid4().hex[:8]}.json"

            if self._storage_service.file_exists(catalog_path):
                self._storage_service.download_file(catalog_path, local_path)

                with open(local_path, "r") as f:
                    self._music_catalog = json.load(f)

                if os.path.exists(local_path):
                    os.remove(local_path)

                self._catalog_loaded = True
                logger.info(
                    f"Loaded music catalog with {len(self._music_catalog)} tracks"
                )
                return self._music_catalog
        except Exception as e:
            logger.warning(f"Failed to load music catalog: {e}")

        # Fall back to default catalog
        self._music_catalog = self.DEFAULT_MUSIC
        self._catalog_loaded = True
        logger.info(
            f"Using default music catalog with {len(self._music_catalog)} tracks"
        )
        return self._music_catalog

    def get_random_music(
        self, mood: Optional[str] = None, genre: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a random music track, optionally filtered by mood or genre.

        Args:
            mood: Optional mood filter
            genre: Optional genre filter

        Returns:
            Music track metadata
        """
        catalog = self._load_catalog()

        # Filter by criteria if provided
        filtered_tracks = catalog

        if mood:
            filtered_tracks = [
                track
                for track in filtered_tracks
                if track.get("mood", "").lower() == mood.lower()
            ]

        if genre:
            filtered_tracks = [
                track
                for track in filtered_tracks
                if track.get("genre", "").lower() == genre.lower()
            ]

        # If no tracks match the criteria, use the full catalog
        if not filtered_tracks:
            logger.warning(
                f"No music tracks match criteria (mood={mood}, genre={genre}). "
                f"Using full catalog."
            )
            filtered_tracks = catalog

        # Select a random track
        track = random.choice(filtered_tracks)

        # Add storage URI
        track["uri"] = get_gcs_uri("audio", "music", track["filename"])

        return track

    def mix_audio_with_music(
        self,
        voice_audio_path: str,
        output_path: str,
        music_track: Optional[Dict[str, Any]] = None,
        music_volume: float = 0.15,
        crossfade_duration: float = 1.0,
    ) -> str:
        """
        Mix voice audio with background music.

        Args:
            voice_audio_path: Path to voice audio file
            output_path: Path to save mixed audio
            music_track: Optional music track metadata (if None, selects random)
            music_volume: Volume level for music (0.0-1.0)
            crossfade_duration: Duration of crossfade in seconds

        Returns:
            Path to mixed audio file
        """
        if not music_track:
            music_track = self.get_random_music()

        # Download music track if needed
        music_path = f"/tmp/music_{uuid.uuid4().hex[:8]}.mp3"

        try:
            self._storage_service.download_file(music_track["uri"], music_path)

            # Get voice audio duration
            voice_probe = ffmpeg.probe(voice_audio_path)
            voice_duration = float(voice_probe["format"]["duration"])

            # Check if music is long enough
            music_probe = ffmpeg.probe(music_path)
            music_duration = float(music_probe["format"]["duration"])

            # If music is too short, loop it
            if music_duration < voice_duration:
                temp_music = f"/tmp/music_loop_{uuid.uuid4().hex[:8]}.mp3"
                loop_count = int(voice_duration / music_duration) + 1

                # Create a concatenation file
                concat_file = f"/tmp/concat_{uuid.uuid4().hex[:8]}.txt"
                with open(concat_file, "w") as f:
                    for _ in range(loop_count):
                        f.write(f"file '{music_path}'\n")

                # Concatenate music file multiple times
                ffmpeg.input(concat_file, format="concat", safe=0).output(
                    temp_music, c="copy", t=voice_duration + 5
                ).run(quiet=True, overwrite_output=True)

                # Replace music path with looped version
                if os.path.exists(music_path):
                    os.remove(music_path)
                music_path = temp_music

                # Clean up concat file
                if os.path.exists(concat_file):
                    os.remove(concat_file)

            # Mix audio with music
            voice = ffmpeg.input(voice_audio_path)
            music = ffmpeg.input(music_path)

            # Apply fades to music
            music = ffmpeg.filter(
                music, "afade", type="in", start_time=0, duration=crossfade_duration
            )
            music = ffmpeg.filter(
                music,
                "afade",
                type="out",
                start_time=max(0, voice_duration - crossfade_duration),
                duration=crossfade_duration,
            )

            # Mix voice and music
            mixed = ffmpeg.filter(
                [voice, music],
                "amix",
                inputs=2,
                dropout_transition=0,
                weights=f"1 {music_volume}",
            )

            # Write output file
            ffmpeg.output(mixed, output_path).run(quiet=True, overwrite_output=True)

            logger.info(f"Mixed voice audio with music track '{music_track['title']}'")

            # Clean up
            if os.path.exists(music_path):
                os.remove(music_path)

            return output_path

        except Exception as e:
            logger.error(f"Error mixing audio with music: {e}")

            # Fall back to just using the voice audio
            try:
                if os.path.exists(voice_audio_path) and not os.path.exists(output_path):
                    ffmpeg.input(voice_audio_path).output(output_path).run(
                        quiet=True, overwrite_output=True
                    )
                    logger.warning("Failed to mix with music, using voice audio only")
            except Exception as e2:
                logger.error(f"Error copying voice audio: {e2}")

            # Clean up
            if os.path.exists(music_path):
                os.remove(music_path)

            return output_path if os.path.exists(output_path) else voice_audio_path
