#!/bin/bash

# Create cron job for daily updates at 2 AM
(crontab -l 2>/dev/null; echo "0 2 * * * cd $(pwd) && python3 ifixit_fetcher.py >> logs/fetcher_\$(date +\%Y\%m\%d).log 2>&1") | crontab -
echo "Crontab has been set up for daily updates at 2 AM"
