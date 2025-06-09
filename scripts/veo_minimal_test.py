#!/usr/bin/env python3
"""
Minimal Veo Test - Uses zero-token approach to test connectivity
"""

import logging
import os
import sys
import time

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("veo-test")

def test_veo_connection():
    """Test Veo API connectivity with zero token usage"""
    try:
        # Try different import approaches to handle different versions of Google Cloud libraries
        try:
            # Approach 1: Standard Google Cloud AI import (newer versions)
            from google.cloud import aiplatform
            from google.cloud.aiplatform.preview import GenerationConfig, GenerativeModel
            
            logger.info("Using google.cloud.aiplatform imports")
            
            # Initialize with the correct region
            aiplatform.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location="us-central1")
            
            # Use Veo 2.0 model
            model_id = os.environ.get("VEO_MODEL", "veo-2.0-generate-001")
            logger.info(f"Using model: {model_id}")
            
            # Initialize the model
            model = GenerativeModel(model_id)
            
            # Create a minimal generation config
            generation_config = GenerationConfig(
                temperature=0.1,
                max_output_tokens=1,
                top_p=0.1,
                top_k=1
            )
            
            # Send a minimal request
            logger.info("Sending minimal request...")
            response = model.generate_content(
                "test",
                generation_config=generation_config
            )
            
        except (ImportError, ModuleNotFoundError):
            # Approach 2: Try VertexAI import (older versions)
            logger.info("Trying alternate import: vertexai")
            from vertexai.preview.generative_models import GenerationConfig, GenerativeModel
            
            # Use Veo 2.0 model
            model_id = os.environ.get("VEO_MODEL", "veo-2.0-generate-001")
            logger.info(f"Using model: {model_id}")
            
            # Initialize the model
            model = GenerativeModel(model_id)
            
            # Create a minimal generation config
            generation_config = GenerationConfig(
                temperature=0.1,
                max_output_tokens=1,
                top_p=0.1,
                top_k=1
            )
            
            # Send a minimal request
            logger.info("Sending minimal request...")
            response = model.generate_content(
                "test",
                generation_config=generation_config
            )
        
        logger.info("✅ Veo connection test passed!")
        return True
    
    except Exception as e:
        logger.error(f"❌ Veo connection test failed: {e}")
        return False

if __name__ == "__main__":
    result = test_veo_connection()
    sys.exit(0 if result else 1) 