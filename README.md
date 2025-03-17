# iFixit Guide Integration

This project fetches repair guides from the iFixit API, stores them in AWS S3 and RDS PostgreSQL, and provides an API to access the data.

## Architecture

- **EC2 Instance**: Runs the data fetcher and API server
- **S3 Buckets**: 
  - Raw data bucket: Stores original API responses
  - Media bucket: Stores guide images
  - Processed data bucket: For future use
- **RDS PostgreSQL**: Stores structured guide data
- **API Server**: Provides access to the stored data

## Components

- `db_setup.py`: Sets up the database schema
- `ifixit_fetcher.py`: Fetches data from the iFixit API
- `api_server.py`: Provides an API to access the data
- `run.sh`: Sets up and runs everything
- `monitor.sh`: Monitors the system
- `backup.sh`: Creates backups
- `index.html`: Simple frontend for viewing guides

## API Endpoints

- `/api/guides`: List all guides with pagination
  - Query parameters:
    - `limit`: Number of guides to return (default: 20, max: 100)
    - `offset`: Number of guides to skip (default: 0)
    - `category`: Filter by category
- `/api/guides/{guide_id}`: Get details for a specific guide

## Setup Instructions

1. Create AWS resources (EC2, S3, RDS)
2. SSH into the EC2 instance
3. Clone this repository
4. Configure `.env` file with credentials
5. Run `./run.sh` to set up and start the system
6. Run `./crontab_setup.sh` to schedule daily updates

## Maintenance

- Run `./monitor.sh` to check system status
- Run `./backup.sh` to create backups
- Check logs in the `logs` directory
