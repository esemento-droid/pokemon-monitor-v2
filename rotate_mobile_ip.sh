#!/bin/bash
# Trigger IP rotation on mi-9t phone (run from VPS)
# Usage: ./rotate_mobile_ip.sh
# Called by bots (via proxy_router.request_ip_rotation()) when IP is banned

LOG="/opt/pokemon-monitor-v2/data/ip_rotation.log"
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"

echo "$(date '+%Y-%m-%d %H:%M:%S') IP ROTATION REQUESTED (from VPS)" >> "$LOG"

OLD_IP=$(cat /opt/pokemon-monitor-v2/mobile_proxy_ip.txt 2>/dev/null || echo "unknown")
echo "$(date '+%Y-%m-%d %H:%M:%S') Current mobile IP: $OLD_IP" >> "$LOG"

# Execute rotation on phone (non-blocking — nohup)
sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TS \
    "nohup ~/bin/rotate_ip.sh > ~/logs/rotate_triggered.log 2>&1 &" 2>> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') Rotation triggered on phone (background)" >> "$LOG"
echo "IP rotation triggered. New IP will appear in ~45s."
