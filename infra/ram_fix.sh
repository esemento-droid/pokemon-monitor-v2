#!/bin/bash
# RAM FIX — eliminates memory leaks, adds protections
# Run as: sudo bash infra/ram_fix.sh
# Safe to re-run (idempotent)
set -e

echo "=== RAM FIX $(date) ==="
echo ""

# ============================================================
# 1. KILL HANGING SESSION_WARMER (zombie patchright/chrome from cron)
# ============================================================
echo "--- 1. Killing hanging session_warmer processes ---"
WARMER_PIDS=$(pgrep -f "session_warmer.py" 2>/dev/null || true)
if [ -n "$WARMER_PIDS" ]; then
    echo "  Found session_warmer PIDs: $WARMER_PIDS"
    kill $WARMER_PIDS 2>/dev/null || true
    sleep 2
    kill -9 $WARMER_PIDS 2>/dev/null || true
    echo "  Killed."
else
    echo "  None running."
fi

# Kill orphaned patchright drivers from warmer (PID 405105, 538172 — started hours ago)
OLD_PATCHRIGHT=$(ps aux | grep "patchright/driver/node" | grep -v grep | awk '{if(systime()-$22 > 3600) print $2}' 2>/dev/null || true)
# Simpler: kill patchright drivers older than the monitor service start
MONITOR_START=$(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp --value 2>/dev/null | xargs -I{} date -d {} +%s 2>/dev/null || echo 0)
if [ "$MONITOR_START" != "0" ]; then
    ps aux | grep "patchright/driver/node" | grep -v grep | while read -r line; do
        PID=$(echo "$line" | awk '{print $2}')
        PPID=$(ps -o ppid= -p $PID 2>/dev/null | tr -d ' ')
        # If parent is init (1) or not in monitor tree — orphan
        if [ "$PPID" = "1" ] || ! pgrep -f "main.py" | grep -q "$PPID" 2>/dev/null; then
            echo "  Killing orphan patchright driver PID $PID (parent $PPID)"
            kill $PID 2>/dev/null || true
        fi
    done
fi
echo ""

# ============================================================
# 2. FLARESOLVERR — restart with memory limit (512MB max)
# ============================================================
echo "--- 2. Restarting FlareSolverr with 512MB memory limit ---"
docker stop flaresolverr 2>/dev/null || true
docker rm flaresolverr 2>/dev/null || true
sleep 2

docker run -d \
    --name flaresolverr \
    --restart unless-stopped \
    --memory=512m \
    --memory-swap=512m \
    -e LOG_LEVEL=info \
    -e TZ=Europe/Warsaw \
    -e HEADLESS=true \
    -p 8191:8191 \
    ghcr.io/flaresolverr/flaresolverr:latest

echo "  FlareSolverr restarted with --memory=512m"
echo ""

# ============================================================
# 3. KILL ZOMBIE CHROME PROCESSES
# ============================================================
echo "--- 3. Cleaning zombie/defunct Chrome processes ---"
ZOMBIES=$(ps aux | grep "\[chromium\] <defunct>" | grep -v grep | awk '{print $2}')
if [ -n "$ZOMBIES" ]; then
    echo "  Found $(echo "$ZOMBIES" | wc -l) zombies"
    echo "$ZOMBIES" | xargs kill -9 2>/dev/null || true
else
    echo "  No zombies found."
fi

# Kill orphaned chromedriver processes not attached to monitor
ORPHAN_CD=$(ps aux | grep "chromedriver" | grep -v grep | awk '{print $2}')
for pid in $ORPHAN_CD; do
    PPID=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' ')
    if [ "$PPID" = "1" ]; then
        echo "  Killing orphan chromedriver PID $pid"
        kill -9 $pid 2>/dev/null || true
    fi
done
echo ""

# ============================================================
# 4. ADD 2GB SWAP (if not exists)
# ============================================================
echo "--- 4. Adding 2GB swap ---"
if swapon --show | grep -q "/swapfile"; then
    echo "  Swap already exists."
else
    if [ -f /swapfile ]; then
        swapon /swapfile 2>/dev/null && echo "  Swap re-enabled." || {
            rm -f /swapfile
            fallocate -l 2G /swapfile
            chmod 600 /swapfile
            mkswap /swapfile
            swapon /swapfile
            echo "  Created and enabled 2GB swap."
        }
    else
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo "  Created and enabled 2GB swap."
    fi
    # Make permanent
    if ! grep -q "/swapfile" /etc/fstab; then
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
        echo "  Added to /etc/fstab (permanent)."
    fi
fi
# Set swappiness low (prefer killing over swapping too much)
sysctl vm.swappiness=10 >/dev/null 2>&1
echo ""

# ============================================================
# 5. INSTALL CHROME ZOMBIE CLEANER CRON
# ============================================================
echo "--- 5. Installing memory guard cron ---"
GUARD_SCRIPT="/opt/pokemon-monitor-v2/infra/memory_guard.sh"
cat > "$GUARD_SCRIPT" << 'GUARD'
#!/bin/bash
# Memory Guard — runs every 5 min via cron
# Kills zombie chrome, orphan patchright, checks FlareSolverr

# Kill defunct/zombie chrome
ps aux | grep "\[chromium\] <defunct>" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null

# Kill session_warmer if running > 10 min (should complete in 2-3 min)
pgrep -f "session_warmer.py" | while read pid; do
    ETIME=$(ps -o etimes= -p $pid 2>/dev/null | tr -d ' ')
    if [ -n "$ETIME" ] && [ "$ETIME" -gt 600 ]; then
        kill $pid 2>/dev/null
        # Also kill its children (patchright/chrome)
        pkill -P $pid 2>/dev/null
    fi
done

# Kill orphaned patchright drivers (parent=1, not from monitor)
ps aux | grep "patchright/driver/node" | grep -v grep | while read line; do
    PID=$(echo "$line" | awk '{print $2}')
    PPID=$(ps -o ppid= -p $PID 2>/dev/null | tr -d ' ')
    ETIME=$(ps -o etimes= -p $PID 2>/dev/null | tr -d ' ')
    # If orphaned (ppid=1) AND running > 20 min — kill
    if [ "$PPID" = "1" ] && [ -n "$ETIME" ] && [ "$ETIME" -gt 1200 ]; then
        kill $PID 2>/dev/null
    fi
done

# If free RAM < 200MB — force-restart FlareSolverr (biggest offender after limit)
FREE_MB=$(free -m | awk '/^Mem:/{print $7}')
if [ "$FREE_MB" -lt 200 ]; then
    logger "memory_guard: LOW RAM (${FREE_MB}MB free) — restarting FlareSolverr"
    docker restart flaresolverr 2>/dev/null
fi
GUARD
chmod +x "$GUARD_SCRIPT"

# Add cron if not exists
CRON_LINE="*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh"
if ! crontab -l 2>/dev/null | grep -qF "memory_guard.sh"; then
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "  Cron installed: memory_guard every 5 min"
else
    echo "  Cron already exists."
fi
echo ""

# ============================================================
# 6. FIX SESSION_WARMER CRON (add timeout)
# ============================================================
echo "--- 6. Fixing session_warmer cron (add 5min timeout) ---"
# Replace old session_warmer cron with timeout version
if crontab -l 2>/dev/null | grep -q "session_warmer.py"; then
    crontab -l | sed 's|.*session_warmer.py.*|0 * * * * cd /opt/pokemon-monitor-v2 \&\& timeout 300 DISPLAY=:99 ./venv/bin/python3 session_warmer.py >> /tmp/warmer.log 2>\&1|' | crontab -
    echo "  Updated: session_warmer now has 5min timeout"
else
    echo "  No session_warmer cron found (OK if not needed)"
fi
echo ""

# ============================================================
# 7. RESTART MONITOR (clean state)
# ============================================================
echo "--- 7. Restarting pokemon-monitor-v2 service ---"
systemctl restart pokemon-monitor-v2
sleep 3
STATUS=$(systemctl is-active pokemon-monitor-v2)
echo "  Monitor status: $STATUS"
echo ""

# ============================================================
# VERIFY
# ============================================================
echo "--- VERIFICATION ---"
echo "RAM:"
free -h
echo ""
echo "Swap:"
swapon --show
echo ""
echo "FlareSolverr:"
docker ps --filter name=flaresolverr --format "{{.Names}}: {{.Status}}"
docker inspect flaresolverr --format '{{.HostConfig.Memory}}' 2>/dev/null | awk '{print "  Memory limit: " $1/1024/1024 "MB"}'
echo ""
echo "Chrome processes: $(ps aux | grep chromium | grep -v grep | wc -l)"
echo "Patchright drivers: $(ps aux | grep patchright/driver | grep -v grep | wc -l)"
echo ""
echo "=== RAM FIX COMPLETE ==="
