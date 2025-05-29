#!/usr/bin/env python3
"""
Test script for TTS fallback functionality.
Tests both ElevenLabs and Google Cloud TTS integration.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add current directory to path to import voiceover_generator
sys.path.insert(0, '.')

from voiceover_generator import (
    generate_voiceover,
    generate_elevenlabs_tts,
    generate_google_tts,
    ElevenLabsQuotaError,
    ElevenLabsAPIError,
    VoiceoverError
)

def test_google_tts():
    """Test Google Cloud TTS functionality."""
    print("🧪 Testing Google Cloud Text-to-Speech...")
    
    test_text = "Hello, this is a test of Google Cloud Text-to-Speech integration."
    
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        output_path = tmp_file.name
    
    try:
        result_path = generate_google_tts(test_text, output_path)
        
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            print(f"✅ Google TTS test successful! File saved: {result_path}")
            print(f"📊 File size: {os.path.getsize(result_path)} bytes")
            return True
        else:
            print("❌ Google TTS test failed: File not created or empty")
            return False
            
    except Exception as e:
        print(f"❌ Google TTS test failed with error: {str(e)}")
        return False
    finally:
        # Clean up test file
        if os.path.exists(output_path):
            os.unlink(output_path)

def test_elevenlabs_tts():
    """Test ElevenLabs TTS functionality."""
    print("🧪 Testing ElevenLabs Text-to-Speech...")
    
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("⚠️ ELEVENLABS_API_KEY not set, skipping ElevenLabs test")
        return None
    
    test_text = "Hello, this is a test of ElevenLabs Text-to-Speech integration."
    
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        output_path = tmp_file.name
    
    try:
        result_path = generate_elevenlabs_tts(test_text, output_path)
        
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            print(f"✅ ElevenLabs TTS test successful! File saved: {result_path}")
            print(f"📊 File size: {os.path.getsize(result_path)} bytes")
            return True
        else:
            print("❌ ElevenLabs TTS test failed: File not created or empty")
            return False
            
    except ElevenLabsQuotaError as e:
        print(f"⚠️ ElevenLabs quota exceeded (expected): {str(e)}")
        return "quota_exceeded"
    except ElevenLabsAPIError as e:
        print(f"❌ ElevenLabs API error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ ElevenLabs test failed with error: {str(e)}")
        return False
    finally:
        # Clean up test file
        if os.path.exists(output_path):
            os.unlink(output_path)

def test_fallback_mechanism():
    """Test the automatic fallback from ElevenLabs to Google TTS."""
    print("🧪 Testing automatic fallback mechanism...")
    
    test_text = "This is a test of the automatic fallback from ElevenLabs to Google Cloud TTS."
    
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        output_path = tmp_file.name
    
    try:
        result_path = generate_voiceover(test_text, output_path)
        
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            print(f"✅ Fallback mechanism test successful! File saved: {result_path}")
            print(f"📊 File size: {os.path.getsize(result_path)} bytes")
            return True
        else:
            print("❌ Fallback mechanism test failed: File not created or empty")
            return False
            
    except VoiceoverError as e:
        print(f"❌ Fallback mechanism failed: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Fallback mechanism test failed with error: {str(e)}")
        return False
    finally:
        # Clean up test file
        if os.path.exists(output_path):
            os.unlink(output_path)

def test_voice_options():
    """Test different Google TTS voice options."""
    print("🧪 Testing different Google TTS voices...")
    
    voices_to_test = [
        "en-US-Studio-O",  # Default
        "en-US-Wavenet-D",
        "en-US-Standard-B",
    ]
    
    test_text = "Testing different voices with Google Cloud Text-to-Speech."
    results = {}
    
    for voice in voices_to_test:
        print(f"  Testing voice: {voice}")
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            output_path = tmp_file.name
        
        try:
            result_path = generate_google_tts(test_text, output_path, voice_name=voice)
            
            if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
                file_size = os.path.getsize(result_path)
                results[voice] = {"success": True, "size": file_size}
                print(f"    ✅ Voice {voice}: Success ({file_size} bytes)")
            else:
                results[voice] = {"success": False, "error": "File not created or empty"}
                print(f"    ❌ Voice {voice}: Failed - File not created or empty")
                
        except Exception as e:
            results[voice] = {"success": False, "error": str(e)}
            print(f"    ❌ Voice {voice}: Failed - {str(e)}")
        finally:
            # Clean up test file
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    return results

def main():
    """Run all TTS tests."""
    print("🚀 Starting TTS Fallback Integration Tests\n")
    
    # Test 1: Google Cloud TTS
    google_result = test_google_tts()
    print()
    
    # Test 2: ElevenLabs TTS (if API key available)
    elevenlabs_result = test_elevenlabs_tts()
    print()
    
    # Test 3: Fallback mechanism
    fallback_result = test_fallback_mechanism()
    print()
    
    # Test 4: Voice options
    voice_results = test_voice_options()
    print()
    
    # Summary
    print("📊 Test Summary:")
    print(f"  Google TTS: {'✅ PASS' if google_result else '❌ FAIL'}")
    
    if elevenlabs_result is None:
        print("  ElevenLabs TTS: ⚠️ SKIPPED (No API key)")
    elif elevenlabs_result == "quota_exceeded":
        print("  ElevenLabs TTS: ⚠️ QUOTA EXCEEDED (Expected)")
    elif elevenlabs_result:
        print("  ElevenLabs TTS: ✅ PASS")
    else:
        print("  ElevenLabs TTS: ❌ FAIL")
    
    print(f"  Fallback Mechanism: {'✅ PASS' if fallback_result else '❌ FAIL'}")
    
    successful_voices = sum(1 for v in voice_results.values() if v["success"])
    total_voices = len(voice_results)
    print(f"  Voice Options: ✅ {successful_voices}/{total_voices} voices working")
    
    # Overall status
    critical_tests_pass = google_result and fallback_result
    
    if critical_tests_pass:
        print("\n🎉 TTS Fallback integration is ready for production!")
        print("💡 Your pipeline now has automatic ElevenLabs → Google TTS fallback")
        if elevenlabs_result == "quota_exceeded":
            print("🔄 Fallback will activate when ElevenLabs quota is exceeded")
    else:
        print("\n❌ Some critical tests failed. Please check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 