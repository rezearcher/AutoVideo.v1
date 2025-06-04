# Text-to-Speech (TTS) Service Documentation

This document explains how the AutoVideo application handles Text-to-Speech services, including the fallback mechanism and troubleshooting procedures.

## TTS Architecture

The application uses a dual-provider approach for Text-to-Speech:

1. **Primary: ElevenLabs TTS** - Higher quality, natural-sounding voices
2. **Fallback: Google Cloud TTS** - Used when ElevenLabs quota is exceeded

## Configuration

### ElevenLabs Setup

1. Set the `ELEVENLABS_API_KEY` environment variable with your API key
2. The application will use ElevenLabs as the primary TTS service when available

### Google Cloud TTS Setup

For proper Google Cloud TTS authentication, either:

1. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to point to a valid service account key file, OR
2. Set the `GOOGLE_CLOUD_SA_KEY` environment variable with the JSON content of the service account key

The application will automatically create a temporary credentials file if the JSON content is provided via `GOOGLE_CLOUD_SA_KEY`.

## Fallback Mechanism

The TTS fallback works as follows:

1. The application attempts to generate audio using ElevenLabs
2. If ElevenLabs fails (quota exceeded or other error), it automatically falls back to Google Cloud TTS
3. If both services fail, the application will report an error

## Diagnostic Endpoint

To check the health of your TTS services, use the `/health/tts` endpoint:

```bash
curl https://your-app-url/health/tts
```

The response will include:

- Status of each TTS service (healthy, error)
- ElevenLabs quota information (if available)
- Google Cloud TTS configuration status
- Overall health assessment

Example response:

```json
{
  "status": "healthy",
  "timestamp": "2025-06-04T08:30:00.123456",
  "services": {
    "elevenlabs": {
      "configured": true,
      "status": "error",
      "error": "HTTP 401: quota_exceeded",
      "quota": {
        "character_count": 10000,
        "character_limit": 10000,
        "remaining_characters": 0
      }
    },
    "google_tts": {
      "configured": true,
      "status": "healthy",
      "credentials_path": "/tmp/google-cloud-credentials.json",
      "voices_available": 426
    }
  }
}
```

## Troubleshooting

### ElevenLabs Issues

- **Quota Exceeded**: Purchase more credits or wait for your quota to reset
- **Authentication Failed**: Verify your API key is correct and active

### Google Cloud TTS Issues

- **Authentication Failed**: 
  - Ensure the service account has the "Cloud Text-to-Speech API User" role
  - Verify the credentials file is accessible or the JSON content is valid
  - Check that the Text-to-Speech API is enabled in your project

- **Quota Exceeded**:
  - Check your Google Cloud Console for quota limits
  - Request a quota increase if needed

## Required IAM Permissions

The service account needs the following permissions:

- `roles/cloudtts.client` or `roles/cloudtts.editor` for Text-to-Speech API access

## Common Error Messages

| Error | Likely Cause | Solution |
|-------|--------------|----------|
| "ElevenLabs quota exceeded" | Out of ElevenLabs credits | Purchase more credits or use Google TTS |
| "Default credentials not found" | Missing or invalid Google credentials | Set up proper service account credentials |
| "Both ElevenLabs and Google TTS failed" | Configuration issues with both services | Check both services' configurations |
| "API not enabled" | Google TTS API not enabled | Enable the API in Google Cloud Console |

## Monitoring

The application logs TTS service usage and fallbacks. Check the application logs for:

- `🔄 Falling back to Google Cloud Text-to-Speech...` - Indicates fallback activation
- `⚠️ ElevenLabs quota exceeded` - Shows when ElevenLabs quota is exceeded
- `❌ Google TTS fallback also failed` - Critical error when both services fail 