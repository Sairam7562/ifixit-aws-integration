#!/bin/bash

# Set up logging
mkdir -p logs
LOG_FILE="logs/setup_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Starting iFixit integration setup ==="
echo "$(date)"

echo "=== Setting up database ==="
python3 db_setup.py

echo "=== Fetching initial data ==="
python3 ifixit_fetcher.py

echo "=== Starting API server ==="
nohup python3 api_server.py > logs/api_server.log 2>&1 &
echo $! > api_server.pid
echo "API server started with PID $(cat api_server.pid)"

echo "=== Setup complete ==="
echo "API Server is running at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):5000"
echo "$(date)"
