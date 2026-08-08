#!/bin/bash
# Proxy watchdog - checks if port 8888 is alive, restarts if dead
# Runs via cron every minute

LOG="/opt/pokemon-monitor-v2/proxy_watchdog.log"
PHONE_KEY="/home/debian/.ssh/phone_proxy"

# Check if proxy port is listening
if ss -tlnp | grep -q ":8888"; then
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY DOWN - attempting restart..." >> "$LOG"

# Step 1: Kill any stale autossh on VPS side
pkill -f "autossh.*8888" 2>/dev/null
sleep 2

# Step 2: Check if we can reach phone via port 2222
if ss -tlnp | grep -q ":2222"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Phone SSH reachable, restarting autossh on phone..." >> "$LOG"
    ssh -p 2222 -i "$PHONE_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes u0_a217@localhost \
        'pkill -f autossh; pkill -f tinyproxy; sleep 2; tinyproxy -d & sleep 1; autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228' 2>> "$LOG"
    
    # Wait and verify
    sleep 5
    if ss -tlnp | grep -q ":8888"; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY RESTORED via phone SSH" >> "$LOG"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY STILL DOWN after phone restart" >> "$LOG"
    fi
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') Phone SSH (2222) also dead - need manual phone restart" >> "$LOG"
fi
