#!/bin/bash

# Start Jupyter Lab in the container
# This script should be run from within the dev container

echo "Starting Jupyter Lab..."
echo "Access at: http://localhost:8888"
echo "Backend API at: http://localhost:8001"
echo ""

# Start Jupyter Lab with proper configuration
uv run jupyter lab \
    --ip=0.0.0.0 \
    --port=8888 \
    --no-browser \
    --allow-root \
    --NotebookApp.token='' \
    --NotebookApp.password='' \
    --notebook-dir=/app