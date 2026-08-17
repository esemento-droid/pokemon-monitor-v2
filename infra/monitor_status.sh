#!/bin/bash
echo "=== STATUS $(date) ==="
echo "monitor: $(systemctl is-active pokemon-monitor-v2 2>/dev/null)"
echo "router: $(systemctl is-active discord-router 2>/dev/null)"
echo "flare: $(docker ps --filter name=flaresolverr --format '{{.Status}}' 2>/dev/null || echo 'no docker?')"
echo ""
echo "--- last 20 journal lines ---"
journalctl -u pokemon-monitor-v2 -n 20 --no-pager 2>&1
echo "=== END ==="
