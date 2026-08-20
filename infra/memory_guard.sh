#!/bin/bash
# ================================================================
# MEMORY GUARD v2 — Proactive memory management
# Runs every 5 min via cron. Self-healing, no accumulation.
#
# STRATEGY:
#   1. Kill zombie/defunct Chrome (immediate, always)
#   2. Kill orphaned Chrome (ppid=1, older than 5 min)
#   3. Kill stuck session_warmer (> 5 min)
#   4. Kill orphaned patchright/playwright drivers (ppid=1, > 10 min)
#   5. Enforce max Chrome count (hard limit 60)
#   6. RAM < 500MB → emergency: restart FlareSolverr
#   7. RAM < 200MB → critical: kill ALL non-monitor Chrome
#   8. Log actions for debugging
# ================================================================

LOG="/opt/pokemon-monitor-v2/data/memory_guard.log"
MAX_CHROME=60
MONITOR_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID --value 2>/dev/null)
NOW=$(date '+%Y-%m-%d %H:%M:%S')

log_action() {
    echo "$NOW $1" >> "$LOG"
}

# --- 1. Kill zombie/defunct Chrome (always, immediate) ---
ZOMBIES=$(ps aux | grep "\[chromium\] <defunct>\|\[chrome\] <defunct>" | grep -v grep | awk '{print $2}')
if [ -n "$ZOMBIES" ]; then
    COUNT=$(echo "$ZOMBIES" | wc -l)
    echo "$ZOMBIES" | xargs kill -9 2>/dev/null
    log_action "KILLED $COUNT zombie Chrome"
fi

# --- 2. Kill orphaned Chrome (ppid=1, older than 5 min = 300s) ---
ORPHANS_KILLED=0
for pid in $(pgrep -f "chromium|chrome-headless-shell" 2>/dev/null); do
    PPID=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' ')
    if [ "$PPID" = "1" ]; then
        ETIME=$(ps -o etimes= -p $pid 2>/dev/null | tr -d ' ')
        if [ -n "$ETIME" ] && [ "$ETIME" -gt 300 ]; then
            kill -9 $pid 2>/dev/null
            ORPHANS_KILLED=$((ORPHANS_KILLED + 1))
        fi
    fi
done
[ $ORPHANS_KILLED -gt 0 ] && log_action "KILLED $ORPHANS_KILLED orphaned Chrome (ppid=1, >5min)"

# --- 3. Kill stuck session_warmer (> 5 min) ---
for pid in $(pgrep -f "session_warmer.py" 2>/dev/null); do
    ETIME=$(ps -o etimes= -p $pid 2>/dev/null | tr -d ' ')
    if [ -n "$ETIME" ] && [ "$ETIME" -gt 300 ]; then
        # Kill warmer and ALL its children (Chrome/patchright)
        pkill -KILL -P $pid 2>/dev/null
        kill -9 $pid 2>/dev/null
        log_action "KILLED stuck session_warmer PID=$pid (${ETIME}s old)"
    fi
done

# --- 4. Kill orphaned patchright/playwright drivers (ppid=1, > 10 min) ---
DRIVERS_KILLED=0
for pid in $(pgrep -f "patchright/driver/node|playwright/driver/node" 2>/dev/null); do
    PPID=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' ')
    if [ "$PPID" = "1" ]; then
        ETIME=$(ps -o etimes= -p $pid 2>/dev/null | tr -d ' ')
        if [ -n "$ETIME" ] && [ "$ETIME" -gt 600 ]; then
            # Kill driver AND its Chrome children
            for child in $(pgrep -P $pid 2>/dev/null); do
                kill -9 $child 2>/dev/null
            done
            kill -9 $pid 2>/dev/null
            DRIVERS_KILLED=$((DRIVERS_KILLED + 1))
        fi
    fi
done
[ $DRIVERS_KILLED -gt 0 ] && log_action "KILLED $DRIVERS_KILLED orphaned patchright/playwright drivers"

# --- 5. Enforce max Chrome count ---
CHROME_COUNT=$(pgrep -fc "chromium|chrome-headless" 2>/dev/null || echo 0)
if [ "$CHROME_COUNT" -gt "$MAX_CHROME" ]; then
    EXCESS=$((CHROME_COUNT - MAX_CHROME))
    # Kill oldest Chrome processes first (by elapsed time)
    ps -eo pid,etimes,cmd | grep -E "chromium|chrome-headless" | grep -v grep | sort -k2 -rn | head -$EXCESS | awk '{print $1}' | xargs kill -9 2>/dev/null
    log_action "LIMIT ENFORCED: killed $EXCESS Chrome (was $CHROME_COUNT, max $MAX_CHROME)"
fi

# --- 6. RAM check → emergency actions ---
FREE_MB=$(free -m | awk '/^Mem:/{print $7}')

if [ "$FREE_MB" -lt 200 ]; then
    # CRITICAL: Kill ALL Chrome not in monitor process tree
    log_action "CRITICAL: RAM=${FREE_MB}MB — killing all non-monitor Chrome"
    for pid in $(pgrep -f "chromium|chrome-headless" 2>/dev/null); do
        # Check if it's in monitor's process tree
        if [ -n "$MONITOR_PID" ] && [ "$MONITOR_PID" != "0" ]; then
            # Walk up parent chain
            CURRENT=$pid
            IN_TREE=0
            for i in $(seq 1 10); do
                PARENT=$(ps -o ppid= -p $CURRENT 2>/dev/null | tr -d ' ')
                if [ "$PARENT" = "$MONITOR_PID" ]; then
                    IN_TREE=1
                    break
                fi
                [ -z "$PARENT" ] || [ "$PARENT" = "1" ] || [ "$PARENT" = "0" ] && break
                CURRENT=$PARENT
            done
            [ $IN_TREE -eq 0 ] && kill -9 $pid 2>/dev/null
        fi
    done
    # Also restart FlareSolverr
    docker restart flaresolverr 2>/dev/null
    log_action "CRITICAL: Restarted FlareSolverr, killed non-monitor Chrome"

elif [ "$FREE_MB" -lt 500 ]; then
    # WARNING: Restart FlareSolverr (frees its accumulated Chrome)
    docker restart flaresolverr 2>/dev/null
    log_action "WARNING: RAM=${FREE_MB}MB — restarted FlareSolverr"
fi

# --- 7. Rotate log (keep last 200 lines) ---
if [ -f "$LOG" ] && [ $(wc -l < "$LOG") -gt 200 ]; then
    tail -100 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
