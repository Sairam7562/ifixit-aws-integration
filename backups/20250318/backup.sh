#!/bin/bash

# Create a backup timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/$TIMESTAMP"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup .env file
cp .env "$BACKUP_DIR/"

# Backup scripts
cp *.py "$BACKUP_DIR/"
cp *.sh "$BACKUP_DIR/"

# Create an inventory of S3 objects (this can take a while for large buckets)
echo "Creating S3 inventory..."
aws s3 ls s3://$(grep RAW_BUCKET .env | cut -d= -f2) --recursive | head -100 > "$BACKUP_DIR/raw_bucket_inventory.txt"
aws s3 ls s3://$(grep MEDIA_BUCKET .env | cut -d= -f2) --recursive | head -100 > "$BACKUP_DIR/media_bucket_inventory.txt"

echo "Backup completed to $BACKUP_DIR"
