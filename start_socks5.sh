#!/bin/bash
# Start/ensure SOCKS5 proxy via SSH dynamic forwarding to mi-9t
# Port 1080 on VPS → routes traffic through phone's mobile network
# Run by cron every 5 min to ensure persistence

if ss -tlnp | grep -q ":1080"; then
    exit 0  # Already running
fi

# Start SOCKS5 via Tailscale
sshpass -p "123" ssh \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -f -N -D 1080 \
    -p 8022 100.127.72.24 2>/dev/null

sleep 2
if ss -tlnp | grep -q ":1080"; then
    echo "$(date) SOCKS5 started on :1080" >> /opt/pokemon-monitor-v2/data/socks5.log
fi
