#!/bin/bash
echo "=== MONITOR + FLARESOLVERR STATUS $(date) ==="
echo ""
echo "--- systemctl pokemon-monitor-v2 ---"
systemctl status pokemon-monitor-v2 --no-pager 2>&1 | head -15
echo ""
echo "--- systemctl discord-router ---"
systemctl status discord-router --no-pager 2>&1 | head -10
echo ""
echo "--- FlareSolverr (docker) ---"
docker ps -a --filter name=flaresolverr --format "{{.Names}} | {{.Status}} | {{.Ports}}" 2>&1
echo ""
echo "--- FlareSolverr test (curl 8191) ---"
curl -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s" --connect-timeout 5 http://127.0.0.1:8191/health 2>&1
echo ""
FSRESP=$(curl -s --connect-timeout 5 http://127.0.0.1:8191/health 2>/dev/null)
echo "  Response: $FSRESP"
echo ""
echo "--- Monitor journal last 5min (errors) ---"
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>&1 | grep -iE "flare|error|timeout|deactivat|exit|crash|failed" | tail -20
echo ""
echo "--- Monitor restarts last 1h ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager 2>&1 | grep -iE "start|stop|deactivat|failed|exit|killed" | tail -10
echo ""
echo "--- Docker logs flaresolverr last 20 lines ---"
docker logs --tail 20 flaresolverr 2>&1
echo ""
echo "=== END ==="
