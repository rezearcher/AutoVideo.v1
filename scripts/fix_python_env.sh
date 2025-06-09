#!/bin/bash
# Script to fix Python environment issues in Cursor

# Unset problematic environment variables
export PYTHONHOME=""
export PYTHONPATH=""

# Display current Python configuration
echo "Fixed Python environment"
echo "======================="
echo "PYTHONHOME=$PYTHONHOME"
echo "PYTHONPATH=$PYTHONPATH"
echo "Python interpreter: $(which python)"
echo ""
echo "To use this fix in your terminal session, run:"
echo "source scripts/fix_python_env.sh"

# You can add any additional Python environment setup here
# For example, activating virtual environment if needed
# source venv/bin/activate

# Run the command passed as arguments
if [ $# -gt 0 ]; then
    echo "Running command: $@"
    "$@"
fi 