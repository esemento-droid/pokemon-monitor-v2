#!/bin/bash
# ================================================================
# PROXY WATCHDOG v2 — Bulletproof with Tailscale fallback
# Runs via cron every minute on VPS
# Checks proxy, if dead → SSH to phone via Tailscale → fix
# ================================================================
LOG="/opt/pokemon-monitor-v2/proxy_watchdog.log"
PHONE_TAILSCALE="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"

# Quick test — proxy alive?
if curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    exit 0
fi

# Try Tailscale direct
if curl -x http://${PHONE_TAILSCALE}:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    # Proxy works on Tailscale but tunnel dead — restart autossh on phone
    echo "$(date '+%Y-%m-%d %H:%M:%S') TUNNEL DEAD but Tailscale proxy OK - restarting autossh" >> "$LOG"
    sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TAILSCALE \
        'pkill autossh; pkill -f "ssh.*8888"; sleep 2; autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228' 2>> "$LOG"
    sleep 5
    if curl -x http://127.0.0.1:8888 -s -o /dev/null --connect-timeout 5 https://google.com 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') TUNNEL RESTORED (autossh restarted)" >> "$LOG"
    fi
    exit 0
fi

# Both dead — full repair via Tailscale SSH
echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY DEAD (tunnel + tailscale) - full repair via Tailscale SSH" >> "$LOG"

# Can we reach phone?
if ! tailscale ping --timeout=5s $PHONE_TAILSCALE >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PHONE UNREACHABLE via Tailscale" >> "$LOG"
    exit 1
fi

# Full repair
sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TAILSCALE bash << 'PHONEFIX'
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
pkill tinyproxy 2>/dev/null
pkill autossh 2>/dev/null
pkill -f "ssh.*8888" 2>/dev/null
sleep 2
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2
autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228
PHONEFIX

sleep 5
if curl -x http://127.0.0.1:8888 -s -o /dev/null --connect-timeout 5 https://google.com 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY RESTORED (full repair via Tailscale)" >> "$LOG"
elif curl -x http://${PHONE_TAILSCALE}:8888 -s -o /dev/null --connect-timeout 5 https://google.com 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY RESTORED on Tailscale (tunnel still dead)" >> "$LOG"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY STILL DEAD after full repair" >> "$LOG"
fi
