#!/bin/bash

# Dartboard Bracket App Launcher
# This script activates the virtual environment and launches the Streamlit app

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to the script directory
cd "$SCRIPT_DIR"

# Activate the virtual environment
source "../.venv/bin/activate"

# Launch the Streamlit app
streamlit run dartboard_app.py
