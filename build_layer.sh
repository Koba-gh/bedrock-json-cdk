#!/bin/bash

# Create a directory for the layer
mkdir -p app/python

# Install dependencies into the layer directory
pip install -r app/requirements.txt -t app/python

echo "Lambda layer dependencies installed successfully!"
