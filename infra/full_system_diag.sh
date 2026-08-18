#!/bin/bash
# PELNA DIAGNOSTYKA SYSTEMU — wszystko w jednym
# bash infra/full_system_diag.sh > /tmp/diag.txt && curl -sF 'file=@/tmp/diag.txt' https://paste.rs

echo "============================================"
echo "FULL SYSTEM DIAGNOSTIC — $(date)"
echo "============================================"
echo ""

echo "=== 1. LOAD + RAM + SWAP ==="
cat /proc/loadavg
free -h | head -3
echo ""

echo "=== 2. ALL PYTHON PROCESSES (monitor + other) ==="
ps -eo pid,ppid,%cpu,%mem,etime,cmd | grep python | grep -v grep
echo ""

echo "=== 3. ALL CHROME/CHROMIUM PROCESSES (count + parent) ==="
echo "Total chrome: $(pgrep -c -f 'chrom' 2>/dev/null || echo 0)"
echo ""
echo "By parent PID:"
ps -eo pid,ppid,cmd | grep -E "chrom" | grep -v grep | awk '{print $2}' | sort | uniq -c | sort -rn | head -10
echo ""
echo "By type:"
ps -eo cmd | grep chrom | grep -v grep | grep -oP '(chromium|chrome-headless|chrome )' | sort | uniq -c
echo ""

echo "=== 4. DOCKER (FlareSolverr) ==="
docker stats --no-stream 2>/dev/null || echo "docker not running"
echo ""

echo "=== 5. TOP 20 BY CPU ==="
ps -eo %cpu,pid,ppid,etime,cmd --sort=-%cpu | head -21
echo ""

echo "=== 6. SYSTEMD SERVICE STATUS ==="
systemctl is-active pokemon-monitor-v2
systemctl show pokemon-monitor-v2 --property=MainPID,ActiveState,SubState,NRestarts 2>/dev/null
echo ""

echo "=== 7. MONITOR PROCESS TREE ==="
MAIN_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID --value 2>/dev/null)
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    pstree -p "$MAIN_PID" 2>/dev/null | head -30
else
    echo "Cannot find main PID"
fi
echo ""

echo "=== 8. SLOW PROCESS — FS REQUESTS (last 5 min) ==="
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | grep -i "flaresolverr\|FlareSolverr" | wc -l
echo "FS errors:"
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | grep -i "flaresolverr.*error\|challenge.*timeout" | wc -l
echo ""
echo "FS requesting shops (last 5 min):"
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | grep -iE "\[SLOW\].*\[INFO\]|\[SLOW\].*error|FlareSolverr" | grep -oP '\[\w+\]' | sort | uniq -c | sort -rn | head -15
echo ""

echo "=== 9. CRON JOBS RUNNING ==="
ps -eo pid,etime,cmd | grep -E "memory_guard|proxy_watchdog|start_socks|health_alert|session_warmer|price_cache" | grep -v grep
echo ""

echo "=== 10. ORPHAN PROCESSES (ppid=1, not system) ==="
ps -eo pid,ppid,%cpu,etime,cmd | awk '$2==1 && $5 ~ /pokemon|chrome|python|node/' | head -10
echo ""

echo "=== 11. NETWORK CONNECTIONS (to localhost:8191 = FlareSolverr) ==="
ss -tn | grep 8191 | wc -l
echo "active connections to FS"
echo ""

echo "=== 12. FAST PROCESS DETAILS ==="
FAST_PID=$(ps -eo pid,cmd | grep "python.*main.py" | grep -v grep | awk '{print $1}' | head -3 | tail -1)
echo "FAST PID: $FAST_PID"
if [ -n "$FAST_PID" ]; then
    ls /proc/$FAST_PID/fd 2>/dev/null | wc -l
    echo "open file descriptors"
    cat /proc/$FAST_PID/status 2>/dev/null | grep -E "Threads|VmRSS|VmSize|voluntary"
fi
echo ""

echo "=== 13. IO WAIT + DISK ==="
iostat -x 1 1 2>/dev/null | tail -5 || echo "iostat not available"
echo ""

echo "=== 14. DUPLICATE SHOPS CHECK ==="
echo "Shops appearing in multiple processes (should be 0):"
journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | grep -oP '\[\w+\] \d+ produktow' | sed 's/\[//;s/\].*//' | sort | uniq -c | sort -rn | awk '$1>5{print}' | head -10
echo ""

echo "=== 15. SCAN SPEED SUMMARY ==="
LOGS=$(journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null)
echo "Total scans: $(echo "$LOGS" | grep -c 'produktow w')"
echo "Timeouts: $(echo "$LOGS" | grep -ci 'timeout')"
echo "Errors: $(echo "$LOGS" | grep -ci 'error')"
echo ""
echo "FAST scans <10s: $(echo "$LOGS" | grep 'FAST.*produktow w' | grep -oP '\d+\.\d+s' | awk -F's' '$1<10' | wc -l)"
echo "FAST scans >60s: $(echo "$LOGS" | grep 'FAST.*produktow w' | grep -oP '\d+\.\d+s' | awk -F's' '$1>60' | wc -l)"
echo ""

echo "============================================"
echo "END DIAGNOSTIC"
echo "============================================"
