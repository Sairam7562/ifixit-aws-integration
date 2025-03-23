#!/bin/bash

clear
echo "========================================================================"
echo "                     IFIXIT DATA INTEGRATION MONITOR                   "
echo "========================================================================"
echo "Last updated: $(date)"
echo

# Get bucket names
raw_bucket=$(grep RAW_BUCKET .env | cut -d= -f2)
media_bucket=$(grep MEDIA_BUCKET .env | cut -d= -f2)

# Check API server status
API_PID_FILE="api_server.pid"
echo "=== API SERVER STATUS ==="
if [ -f "$API_PID_FILE" ] && ps -p $(cat "$API_PID_FILE") > /dev/null; then
    echo "Status: RUNNING with PID $(cat $API_PID_FILE)"
    echo "Uptime: $(ps -o etime= -p $(cat $API_PID_FILE))"
else
    echo "Status: NOT RUNNING! Restarting..."
    nohup python3 enhanced_api_server.py > logs/api_server.log 2>&1 &
    echo $! > "$API_PID_FILE"
    echo "API server restarted with PID $(cat $API_PID_FILE)"
fi
echo

# Check Web server status
WEB_PID_FILE="webserver.pid"
echo "=== WEB SERVER STATUS ==="
if [ -f "$WEB_PID_FILE" ] && ps -p $(cat "$WEB_PID_FILE") > /dev/null; then
    echo "Status: RUNNING with PID $(cat $WEB_PID_FILE)"
    echo "Uptime: $(ps -o etime= -p $(cat $WEB_PID_FILE))"
else
    echo "Status: NOT RUNNING! Restarting..."
    python3 -m http.server 8080 --directory . &
    echo $! > "$WEB_PID_FILE"
    echo "Web server restarted with PID $(cat $WEB_PID_FILE)"
fi
echo

echo "=== FETCH PROCESS STATUS ==="
if ps aux | grep -v grep | grep -q "enhanced_ifixit_fetcher.py"; then
    echo "Status: RUNNING"
    pid=$(ps aux | grep -v grep | grep "enhanced_ifixit_fetcher.py" | awk '{print $2}')
    echo "Process ID: $pid"
    echo "Running since: $(ps -p $pid -o lstart=)"
else
    echo "Status: NOT RUNNING"
fi
echo

echo "=== LATEST LOG ENTRIES ==="
if [ -f logs/api_server.log ]; then
    echo "API Server logs (last 5 lines):"
    tail -n 5 logs/api_server.log
else
    echo "API Server log file not found"
fi
echo

if [ -f fetcher_full.log ]; then
    echo "Fetcher logs (last 5 lines):"
    tail -n 5 fetcher_full.log
else
    echo "Fetcher log file not found"
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
    
    # Get counts of different tables
    cursor.execute('SELECT COUNT(*) FROM guides')
    guide_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM steps')
    step_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM media')
    media_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM categories')
    category_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tags')
    tag_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM products')
    product_count = cursor.fetchone()[0]
    
    print(f'Guides: {guide_count}, Steps: {step_count}, Media: {media_count}')
    print(f'Categories: {category_count}, Tags: {tag_count}, Products: {product_count}')
    
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

echo "=== RECENT API REQUESTS ==="
if [ -f logs/api_server.log ]; then
    grep "Requesting:" logs/api_server.log | tail -10
else
    echo "API server log file not found"
fi
echo

echo "========================================================================"
echo "API Server URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):5000"
echo "Web Interface URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo "========================================================================"
echo "To continuously monitor: watch -n 30 ./enhanced_monitor.sh"
echo "To manually restart data fetch: python3 enhanced_ifixit_fetcher.py"
echo "========================================================================"
