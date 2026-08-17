#!/bin/bash
# ================================================================
# PROXY WATCHDOG v3 — Handles 503/MaxClients + DNS issues
# Runs via cron every minute on VPS
# Checks proxy, if dead → SSH to phone via Tailscale → fix
# ================================================================
LOG="/opt/pokemon-monitor-v2/proxy_watchdog.log"
PHONE_TAILSCALE="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"

# Quick test — proxy alive? Must get HTTP 200 or 301 (503 = broken!)
if curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    exit 0
fi

# Try Tailscale direct — also must be 200/301 (503 = tinyproxy broken)
if curl -x http://${PHONE_TAILSCALE}:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    # Proxy works on Tailscale but tunnel dead — restart autossh on phone
    echo "$(date '+%Y-%m-%d %H:%M:%S') TUNNEL DEAD but Tailscale proxy OK - restarting autossh" >> "$LOG"
    sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TAILSCALE \
        'pkill autossh; pkill -f "ssh.*8888"; sleep 2; autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228' 2>> "$LOG"
    sleep 5
    if curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') TUNNEL RESTORED (autossh restarted)" >> "$LOG"
    fi
    exit 0
fi

# Both dead (no 200/301 from either path) — full repair via Tailscale SSH
echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY DEAD (tunnel + tailscale) - full repair via Tailscale SSH" >> "$LOG"

# Can we reach phone?
if ! tailscale ping --timeout=5s $PHONE_TAILSCALE >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PHONE UNREACHABLE via Tailscale" >> "$LOG"
    exit 1
fi

# Full repair — force kill, fix DNS, set MaxClients high, restart everything
sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TAILSCALE bash << 'PHONEFIX'
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export PREFIX="/data/data/com.termux/files/usr"

# Force kill (regular kill may not release ports)
pkill -9 tinyproxy 2>/dev/null
pkill -9 autossh 2>/dev/null
pkill -9 -f "ssh.*8888" 2>/dev/null
sleep 3

# Fix DNS (Android may lose resolver after network change)
echo "nameserver 1.1.1.1" > $PREFIX/etc/resolv.conf
echo "nameserver 8.8.8.8" >> $PREFIX/etc/resolv.conf

# Ensure MaxClients is 200 (prevents connection exhaustion)
sed -i 's/MaxClients [0-9]*/MaxClients 200/' $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null

# Start tinyproxy
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2

# Start autossh tunnel
autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228
PHONEFIX

sleep 8
if curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY RESTORED (full repair)" >> "$LOG"
elif curl -x http://${PHONE_TAILSCALE}:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null | grep -q "200\|301"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY RESTORED on Tailscale only (tunnel still dead)" >> "$LOG"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') PROXY STILL DEAD after full repair — phone internet may be down" >> "$LOG"
fi
