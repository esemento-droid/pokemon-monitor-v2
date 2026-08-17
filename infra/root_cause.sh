#!/bin/bash
echo "=== ROOT CAUSE ANALYSIS $(date) ==="
echo ""

echo "--- 1. WHO runs session_warmer? ---"
echo "  debian crontab:"
crontab -u debian -l 2>/dev/null | grep -i "warm\|session" || echo "    (none)"
echo "  root crontab:"
crontab -l 2>/dev/null | grep -i "warm\|session" || echo "    (none)"
echo "  /etc/cron.d/:"
grep -r "warm\|session" /etc/cron.d/ 2>/dev/null || echo "    (none)"
echo "  systemd timers:"
systemctl list-timers --all 2>/dev/null | grep -i "warm\|session" || echo "    (none)"
echo "  systemd service files:"
grep -r "session_warmer" /etc/systemd/ 2>/dev/null || echo "    (none)"
echo "  pokemon-monitor-v2 service file:"
cat /etc/systemd/system/pokemon-monitor-v2.service 2>/dev/null
echo ""

echo "--- 2. FULL debian crontab ---"
crontab -u debian -l 2>/dev/null || echo "  (empty)"
echo ""

echo "--- 3. FlareSolverr config (env vars) ---"
docker inspect flaresolverr --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null
echo ""

echo "--- 4. How many Chrome per NODRIVER shop? ---"
echo "  runner.py processes now:"
ps aux | grep "runner.py" | grep -v grep | awk '{print "  PID="$2, $11, $12, $13}'
echo ""
echo "  patchright/playwright drivers now:"
ps aux | grep -E "(patchright|playwright)/driver" | grep -v grep | awk '{printf "  PID=%s PPID=%s RSS=%sMB\n", $2, $(NF-1), $6/1024}'
echo ""

echo "--- 5. Process tree of monitor ---"
MONITOR_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID --value 2>/dev/null)
echo "  Main PID: $MONITOR_PID"
if [ -n "$MONITOR_PID" ] && [ "$MONITOR_PID" != "0" ]; then
    pstree -p $MONITOR_PID 2>/dev/null | head -30
fi
echo ""

echo "--- 6. All chromedriver instances (who owns them?) ---"
ps aux | grep chromedriver | grep -v grep | awk '{print "  PID="$2, "PPID="}'
for pid in $(pgrep -f chromedriver); do
    PPID=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' ')
    CMD=$(ps -o cmd= -p $PPID 2>/dev/null | head -c 80)
    echo "  chromedriver PID=$pid parent=$PPID ($CMD)"
done
echo ""

echo "--- 7. WARP status (378MB!) ---"
systemctl is-active warp-svc 2>/dev/null || echo "not a service"
warp-cli status 2>/dev/null || echo "warp-cli not found"
echo ""

echo "=== END ROOT CAUSE ==="
