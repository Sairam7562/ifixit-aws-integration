#!/bin/bash

clear
echo "======================================================================"
echo "                     IFIXIT DATA INTEGRATION MONITOR                  "
echo "======================================================================"
echo "Last updated: $(date)"
echo

# Get bucket names
raw_bucket=$(grep RAW_BUCKET .env | cut -d= -f2)
media_bucket=$(grep MEDIA_BUCKET .env | cut -d= -f2)

echo "=== FETCH PROCESS STATUS ==="
if ps aux | grep -v grep | grep -q "ifixit_fetcher.py"; then
    echo "Status: RUNNING"
    pid=$(ps aux | grep -v grep | grep "ifixit_fetcher.py" | awk '{print $2}')
    echo "Process ID: $pid"
    echo "Running since: $(ps -p $pid -o lstart=)"
else
    echo "Status: NOT RUNNING"
fi
echo

echo "=== LATEST LOG ENTRIES ==="
if [ -f fetcher_full.log ]; then
    tail -n 5 fetcher_full.log
else
    echo "Log file not found"
fi
echo

echo "=== CURRENT STATS ==="
if [ -f fetch_stats.json ]; then
    cat fetch_stats.json
else
    echo "Stats file not found"
fi
echo

echo "=== DATABASE COUNTS ==="
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
    cursor.execute('SELECT COUNT(*) FROM guides')
    guide_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM steps')
    step_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM media')
    media_count = cursor.fetchone()[0]
    print(f'Guides: {guide_count}, Steps: {step_count}, Media: {media_count}')
    
    # Get database size
    cursor.execute(\"\"\"
        SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size
    \"\"\")
    db_size = cursor.fetchone()[0]
    print(f'Database Size: {db_size}')
    
    conn.close()
except Exception as e:
    print(f'Error connecting to database: {e}')
"
echo

echo "=== S3 STORAGE USAGE ==="
echo "Raw data bucket ($raw_bucket):"
aws s3 ls s3://$raw_bucket --recursive --summarize | grep -E "Total Size|Total Objects" || echo "Failed to get S3 stats"

echo
echo "Media bucket ($media_bucket):"
aws s3 ls s3://$media_bucket --recursive --summarize | grep -E "Total Size|Total Objects" || echo "Failed to get S3 stats"
echo

echo "=== SYSTEM RESOURCES ==="
echo "Disk usage:"
df -h | grep -v tmpfs
echo "Disk usage percentage: $(df -h / | awk 'NR==2 {print $5}')"
echo
echo "Memory usage:"
free -h
echo
echo "CPU usage:"
top -bn1 | head -n 5
echo

echo "=== NETWORK ACTIVITY ==="
echo "Network connections:"
netstat -tunp 2>/dev/null | grep python | wc -l | xargs echo "Active connections:"
echo

echo "=== SERVICES STATUS ==="
echo "API Server:"
if ps aux | grep -v grep | grep -q "api_server.py"; then
    echo "RUNNING"
else
    echo "NOT RUNNING"
fi

echo "Web Server (port 8080):"
if ps aux | grep -v grep | grep -q "http.server.*8080"; then
    echo "RUNNING"
else
    echo "NOT RUNNING"
fi
echo

echo "======================================================================"
echo "To continuously monitor: watch -n 30 ./monitor_fetch.sh"
echo "======================================================================"
