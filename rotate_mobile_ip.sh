#!/bin/bash
# Trigger IP rotation on mi-9t phone (run from VPS)
# Usage: ./rotate_mobile_ip.sh [--force]
# Called by bots (via proxy_router.request_ip_rotation()) when IP is banned
#
# NOTE: Orange PL SIM has STATIC IP — rotation does nothing except disrupt connectivity.
# This script will skip rotation unless a new dynamic SIM is detected.
# Use --force to override (for testing after SIM swap).

LOG="/opt/pokemon-monitor-v2/data/ip_rotation.log"
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"
KNOWN_STATIC_IP="37.47.128.183"

# Check current IP
CURRENT_IP=$(cat /opt/pokemon-monitor-v2/mobile_proxy_ip.txt 2>/dev/null || echo "unknown")

# Skip rotation if Orange PL static IP (unless --force)
if [ "$1" != "--force" ] && [ "$CURRENT_IP" = "$KNOWN_STATIC_IP" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') ROTATION SKIPPED — Orange PL static IP ($KNOWN_STATIC_IP). Use --force or swap SIM." >> "$LOG"
    echo "Rotation skipped: Orange PL static IP. Airplane mode won't change it."
    exit 0
fi

# If IP is unknown, check live before disrupting connectivity
if [ "$1" != "--force" ] && [ "$CURRENT_IP" = "unknown" ]; then
    LIVE_IP=$(curl --socks5-hostname 127.0.0.1:1080 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null)
    if [ -z "$LIVE_IP" ]; then
        LIVE_IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null)
    fi
    if [ "$LIVE_IP" = "$KNOWN_STATIC_IP" ]; then
        echo "$LIVE_IP" > /opt/pokemon-monitor-v2/mobile_proxy_ip.txt
        echo "$(date '+%Y-%m-%d %H:%M:%S') ROTATION SKIPPED — detected static IP ($LIVE_IP)" >> "$LOG"
        echo "Rotation skipped: static IP detected."
        exit 0
    fi
    # Unknown/new IP — might be new SIM, proceed with rotation
    [ -n "$LIVE_IP" ] && CURRENT_IP="$LIVE_IP"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') IP ROTATION REQUESTED (from VPS)" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') Current mobile IP: $CURRENT_IP" >> "$LOG"

# Execute rotation on phone (non-blocking — nohup)
sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TS \
    "nohup ~/bin/rotate_ip.sh > ~/logs/rotate_triggered.log 2>&1 &" 2>> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') Rotation triggered on phone (background)" >> "$LOG"
echo "IP rotation triggered. New IP will appear in ~45s."
