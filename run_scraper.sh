#!/bin/bash

# Ensure playwright is installed (already in Docker, but keeping for standalone usage)
pip install rebrowser-playwright curl_cffi lxml beautifulsoup4 requests

# Ensure chromium is installed for playwright (using --with-deps for linux environments if not in Docker)
python3 -m rebrowser_playwright install --with-deps chromium

# Run the python script
python3 scrape.py targets.tsv
