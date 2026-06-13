#!/bin/bash

# Start the simple and secure web server to serve .txt output files
# You can pass a custom port as the first argument, defaults to 57275
PORT=${1:-57275}
python3 server.py "$PORT"
