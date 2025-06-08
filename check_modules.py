#!/usr/bin/env python3
"""
Simple script to check if the required modules can be imported
"""

import os
import sys

print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Python path: {sys.path}")

try:
    import google.cloud.aiplatform

    print("Successfully imported google.cloud.aiplatform")
except ImportError as e:
    print(f"Failed to import google.cloud.aiplatform: {e}")

try:
    import vertexai

    print("Successfully imported vertexai")
except ImportError as e:
    print(f"Failed to import vertexai: {e}")

try:
    import vertexai.preview.generative_models

    print("Successfully imported vertexai.preview.generative_models")
except ImportError as e:
    print(f"Failed to import vertexai.preview.generative_models: {e}")

try:
    import google.cloud.storage

    print("Successfully imported google.cloud.storage")
except ImportError as e:
    print(f"Failed to import google.cloud.storage: {e}")
