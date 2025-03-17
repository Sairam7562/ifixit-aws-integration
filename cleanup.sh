#!/bin/bash

# WARNING: This script will delete all your AWS resources for this project
# Only run it if you want to completely remove the project

# Confirm before proceeding
echo "WARNING: This will delete all AWS resources for the iFixit integration project."
echo "Type 'DELETE' to confirm:"
read confirmation

if [ "$confirmation" != "DELETE" ]; then
    echo "Cleanup cancelled."
    exit 1
fi

echo "Proceeding with cleanup..."

# Stop the API server
if [ -f "api_server.pid" ]; then
    kill -9 $(cat api_server.pid) || true
    rm api_server.pid
    echo "API server stopped"
fi

# Get the AWS resource names from .env
source .env
EC2_INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

# Log the resources that will be deleted
echo "The following resources will be deleted:"
echo "- EC2 Instance: $EC2_INSTANCE_ID"
echo "- S3 Buckets:"
echo "  - $RAW_BUCKET"
echo "  - $MEDIA_BUCKET"
echo "  - $PROCESSED_BUCKET"
echo "- RDS Database at: $DB_HOST"

echo "Cleanup script created. To execute, you need to manually terminate the EC2 instance, delete the S3 buckets, and delete the RDS database from the AWS Console."

