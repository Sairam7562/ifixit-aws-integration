#!/bin/bash

# Check API server status
API_PID_FILE="api_server.pid"
if [ -f "$API_PID_FILE" ] && ps -p $(cat "$API_PID_FILE") > /dev/null; then
    echo "API server is running with PID $(cat $API_PID_FILE)"
else
    echo "API server is not running! Restarting..."
    nohup python3 api_server.py > logs/api_server.log 2>&1 &
    echo $! > "$API_PID_FILE"
    echo "API server restarted with PID $(cat $API_PID_FILE)"
fi

# Check disk space
echo "Disk space usage:"
df -h

# Check memory usage
echo "Memory usage:"
free -h

# Check database connection
echo "Testing database connection:"
python3 -c "
import psycopg2
from dotenv import load_dotenv
import os
load_dotenv()
try:
    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT', '5432')
    )
    cursor = conn.cursor()
    cursor.execute('SELECT count(*) FROM guides')
    count = cursor.fetchone()[0]
    print(f'Successfully connected to database. {count} guides stored.')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'Error connecting to database: {e}')
"

# Check S3 buckets
echo "S3 bucket status:"
aws s3 ls s3://$(grep RAW_BUCKET .env | cut -d= -f2) | head -5
echo "..."
aws s3 ls s3://$(grep MEDIA_BUCKET .env | cut -d= -f2) | head -5
echo "..."
