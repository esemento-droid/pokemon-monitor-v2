#!/bin/bash
echo "=== MORNING CHECK $(date) ==="
echo ""

echo "--- 1. Monitor uptime ---"
systemctl status pokemon-monitor-v2 --no-pager 2>&1 | grep -E "Active:|Main PID"
echo ""

echo "--- 2. RAM ---"
free -h | head -2
echo "Swap:"
swapon --show 2>/dev/null
echo ""

echo "--- 3. Chrome count ---"
echo "Chrome processes: $(pgrep -fc 'chromium|chrome-headless' 2>/dev/null || echo 0)"
echo "Patchright drivers: $(pgrep -fc 'patchright/driver' 2>/dev/null || echo 0)"
echo ""

echo "--- 4. FlareSolverr ---"
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}" flaresolverr 2>/dev/null
echo ""

echo "--- 5. Night IP test ---"
if [ -f /opt/pokemon-monitor-v2/infra/night_ip_test.sh ]; then
    bash /opt/pokemon-monitor-v2/infra/night_ip_test.sh check 2>&1
else
    echo "  night_ip_test.sh not found"
fi
echo ""

echo "--- 6. Proxy quick check ---"
echo -n "  Tunnel: "
curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1
echo ""
echo -n "  Tailscale: "
curl -x http://100.127.72.24:8888 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1
echo ""
echo -n "  SOCKS5: "
curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 https://api.ipify.org 2>&1
echo ""
echo -n "  Mobile IP: "
curl -x http://127.0.0.1:8888 -s --connect-timeout 5 https://api.ipify.org 2>/dev/null
echo ""
echo ""

echo "--- 7. memory_guard log (last 10 actions) ---"
tail -10 /opt/pokemon-monitor-v2/data/memory_guard.log 2>/dev/null || echo "  (no log yet)"
echo ""

echo "--- 8. Monitor errors last 30min ---"
journalctl -u pokemon-monitor-v2 --since "30 min ago" --no-pager -o cat 2>/dev/null | grep -iE "error|crash|killed|oom|deactivat" | tail -10
echo "  (empty = no errors)"
echo ""

echo "--- 9. Disk ---"
df -h / | tail -1
echo ""

echo "=== END MORNING CHECK ==="
