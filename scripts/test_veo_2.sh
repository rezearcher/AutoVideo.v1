#!/bin/bash
# Script to test Veo 2.0 model with fixed Python environment

# Source the fix_python_env script to ensure correct environment
source "$(dirname "$0")/fix_python_env.sh"

# Set Veo model explicitly
export VEO_MODEL="veo-2.0-generate-001"

echo "Testing Veo 2.0 model..."
echo "VEO_MODEL=$VEO_MODEL"

# Run the minimal test
python "$(dirname "$0")/veo_minimal_test.py" 