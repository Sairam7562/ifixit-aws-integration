#!/bin/bash

# Set up logging
mkdir -p logs
LOG_FILE="logs/setup_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Starting iFixit integration setup ==="
echo "$(date)"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Please create a .env file with the required credentials."
    exit 1
fi

# Install required Python packages
echo "=== Installing dependencies ==="
pip3 install -r requirements.txt

echo "=== Setting up database ==="
python3 enhanced_db_setup.py

echo "=== Creating AWS S3 buckets if they don't exist ==="
source .env
aws s3 mb s3://$RAW_BUCKET --region us-east-1 || true
aws s3 mb s3://$MEDIA_BUCKET --region us-east-1 || true
aws s3 mb s3://$PROCESSED_BUCKET --region us-east-1 || true

echo "=== Fetching initial data ==="
python3 enhanced_ifixit_fetcher.py

echo "=== Starting API server ==="
nohup python3 enhanced_api_server.py > logs/api_server.log 2>&1 &
echo $! > api_server.pid
echo "API server started with PID $(cat api_server.pid)"

echo "=== Starting web server for UI access ==="
python3 -m http.server 8080 --directory . &
echo $! > webserver.pid
echo "Web server started with PID $(cat webserver.pid)"

echo "=== Setup complete ==="
echo "API Server is running at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):5000"
echo "Web Interface is available at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo "$(date)"

echo ""
echo "=== Available API Endpoints ==="
echo "- GET /api/guides            # List all guides with pagination"
echo "- GET /api/guides/{id}       # Get specific guide details"
echo "- GET /api/categories        # List all categories"
echo "- GET /api/categories/{title} # Get specific category"
echo "- GET /api/products          # List all products"
echo "- GET /api/products/{itemcode} # Get specific product"
echo "- GET /api/tags              # List all tags"
echo "- GET /api/search?q={query}  # Search across all content"
echo "- GET /api/stats             # Get system statistics"
echo ""
echo "Run './monitor.sh' to check system status."
