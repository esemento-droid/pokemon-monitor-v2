#!/bin/bash
# Proxy diagnostics — check all 3 paths + phone status
echo "=== PROXY DIAGNOSTICS $(date) ==="
echo ""

echo "--- 1. HTTP Tunnel (127.0.0.1:8888) ---"
RESULT=$(curl -x http://127.0.0.1:8888 -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1)
echo "  Connect test: $RESULT"
if IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 https://api.ipify.org 2>/dev/null); then
    echo "  Mobile IP: $IP"
else
    echo "  FAILED — no response"
fi
echo ""

echo "--- 2. Tailscale Direct (100.127.72.24:8888) ---"
RESULT=$(curl -x http://100.127.72.24:8888 -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1)
echo "  Connect test: $RESULT"
if IP=$(curl -x http://100.127.72.24:8888 -s --connect-timeout 5 https://api.ipify.org 2>/dev/null); then
    echo "  Mobile IP: $IP"
else
    echo "  FAILED — no response"
fi
echo ""

echo "--- 3. SOCKS5 (127.0.0.1:1080) ---"
RESULT=$(curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1)
echo "  Connect test: $RESULT"
if IP=$(curl --socks5-hostname 127.0.0.1:1080 -s --connect-timeout 5 https://api.ipify.org 2>/dev/null); then
    echo "  Mobile IP: $IP"
else
    echo "  FAILED — no response"
fi
echo ""

echo "--- 4. Tailscale Ping (mi-9t) ---"
tailscale ping -c 3 --timeout 5s 100.127.72.24 2>&1 | head -5
echo ""

echo "--- 5. SSH to Phone (process check) ---"
if command -v sshpass >/dev/null 2>&1; then
    if sshpass -p 123 ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -p 8022 100.127.72.24 'echo "SSH OK"; ps aux | grep -E "(tinyproxy|autossh|crond)" | grep -v grep; echo ""; echo "Uptime:"; uptime' 2>/dev/null; then
        echo "  Phone SSH: OK"
    else
        echo "  Phone SSH: FAILED (unreachable or timeout)"
    fi
else
    echo "  sshpass not installed — skipping SSH check"
    echo "  Manual: sshpass -p 123 ssh -p 8022 100.127.72.24 'ps aux | grep tinyproxy'"
fi
echo ""

echo "--- 6. VPS Tunnel Port Check ---"
ss -tlnp | grep -E ":(8888|1080)" 2>/dev/null || echo "  No listeners on 8888/1080!"
echo ""

echo "--- 7. Proxy Watchdog Status ---"
journalctl -u cron --since "10 min ago" --no-pager 2>/dev/null | grep -i "proxy_watchdog\|start_socks5" | tail -10
echo ""

echo "--- 8. Monitor Health (last errors) ---"
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | grep -iE "proxy|timeout|connection|refused|error" | tail -10
echo ""

echo "=== END DIAGNOSTICS ==="
