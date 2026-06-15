#!/bin/bash

# Ensure dependencies are installed (already in Docker, but keeping for standalone usage)
pip install curl_cffi lxml beautifulsoup4 requests

# Run the python script
python3 scrape.py targets.tsv
