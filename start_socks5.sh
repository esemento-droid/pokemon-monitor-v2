#!/bin/bash
# Start/ensure SOCKS5 proxy via SSH dynamic forwarding to mi-9t
# Port 1080 on VPS → routes traffic through phone's mobile network
# Run by cron every 5 min to ensure persistence

SOCKS_PORT=1080
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"
LOG="/opt/pokemon-monitor-v2/data/socks5.log"

# If port is bound, verify it actually works
if ss -tlnp | grep -q ":${SOCKS_PORT}"; then
    # Real connectivity test — not just port check
    if curl --socks5-hostname 127.0.0.1:${SOCKS_PORT} -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 https://www.google.com 2>/dev/null | grep -q "200\|301"; then
        exit 0  # Working correctly
    fi
    # Port bound but SOCKS5 not working — zombie process, kill it
    echo "$(date) ZOMBIE SOCKS5 detected (port bound, no connectivity) — killing" >> "$LOG"
    pkill -9 -f "ssh.*${SOCKS_PORT}" 2>/dev/null
    sleep 2
fi

# Start SOCKS5 via Tailscale (primary path)
sshpass -p "$PHONE_PASS" ssh \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ConnectTimeout=10 \
    -f -N -D ${SOCKS_PORT} \
    -p $PHONE_PORT $PHONE_TS 2>/dev/null

sleep 3

# Verify it started and works
if curl --socks5-hostname 127.0.0.1:${SOCKS_PORT} -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 https://www.google.com 2>/dev/null | grep -q "200\|301"; then
    echo "$(date) SOCKS5 started on :${SOCKS_PORT} (Tailscale)" >> "$LOG"
    exit 0
fi

# Tailscale failed — try reverse tunnel fallback (port 2222)
echo "$(date) SOCKS5 Tailscale path failed, trying reverse tunnel :2222" >> "$LOG"
pkill -9 -f "ssh.*${SOCKS_PORT}" 2>/dev/null
sleep 1

sshpass -p "$PHONE_PASS" ssh \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ConnectTimeout=10 \
    -f -N -D ${SOCKS_PORT} \
    -p 2222 127.0.0.1 2>/dev/null

sleep 3

if curl --socks5-hostname 127.0.0.1:${SOCKS_PORT} -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 8 https://www.google.com 2>/dev/null | grep -q "200\|301"; then
    echo "$(date) SOCKS5 started on :${SOCKS_PORT} (reverse tunnel)" >> "$LOG"
else
    echo "$(date) SOCKS5 FAILED — both paths dead" >> "$LOG"
fi
