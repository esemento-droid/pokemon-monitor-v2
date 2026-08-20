#!/bin/bash
# Deep diagnostic — full system picture, compact output
# Usage: bash infra/deep_diag.sh [HOURS]
# Default: last 3 hours. Pass argument for custom window.
exec > /tmp/deep_diag.txt 2>&1

HOURS=${1:-3}
WINDOW="${HOURS} hours ago"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  DEEP DIAGNOSTIC $(date '+%Y-%m-%d %H:%M') (last ${HOURS}h)            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# === 1. SYSTEM OVERVIEW ===
echo "=== 1. SYSTEM ==="
echo "  Uptime: $(uptime -p)"
echo "  Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')"
free -m | awk '/Mem:/ {printf "  RAM: %dMB/%dMB used (%dMB free, %dMB available)\n", $3, $2, $4, $7}'
free -m | awk '/Swap:/ {printf "  Swap: %dMB/%dMB\n", $3, $2}'
echo "  Chrome: $(pgrep -c chrom 2>/dev/null || echo 0) processes, $(ps aux | grep -i chrom | grep -v grep | awk '{sum+=$6} END {printf "%.0f", sum/1024}')MB"
echo ""

# === 2. SERVICE + PROCESSES ===
echo "=== 2. SERVICE ==="
MAIN_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID 2>/dev/null | cut -d= -f2)
ACTIVE_TS=$(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
echo "  PID: $MAIN_PID | Since: $ACTIVE_TS"
printf "  %-10s %-8s %-6s %-6s %-6s\n" "ROLE" "PID" "%CPU" "%MEM" "RSS_MB"
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    for PID in $MAIN_PID $(pgrep -P $MAIN_PID 2>/dev/null | head -6); do
        [ -d "/proc/$PID" ] || continue
        CPU=$(ps -p $PID -o %cpu= 2>/dev/null | tr -d ' ')
        MEM=$(ps -p $PID -o %mem= 2>/dev/null | tr -d ' ')
        RSS=$(($(ps -p $PID -o rss= 2>/dev/null | tr -d ' ') / 1024))
        printf "  %-10s %-8s %-6s %-6s %-6s\n" "PID-$PID" "$PID" "$CPU" "$MEM" "${RSS}M"
    done
fi
echo ""

# === 3. PROXY ===
echo "=== 3. PROXY ==="
printf "  HTTP(8888): "
timeout 5 curl -x http://127.0.0.1:8888 -s -w "%{http_code} %{time_total}s IP=" --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
printf "  Tailscale:  "
timeout 5 curl -x http://100.127.72.24:8888 -s -w "%{http_code} %{time_total}s IP=" --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
printf "  SOCKS5:     "
timeout 5 curl --socks5-hostname 127.0.0.1:1080 -s -w "%{http_code} %{time_total}s IP=" --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
printf "  VPS direct: "
timeout 5 curl -s --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo ""

# === 4. PHONE ===
echo "=== 4. PHONE (Mi 9T) ==="
PING_AVG=$(timeout 5 ping -c 2 -W 2 100.127.72.24 2>/dev/null | tail -1 | awk -F'/' '{print $5}')
echo "  Ping: ${PING_AVG:-UNREACHABLE}ms"
PHONE_CRON=$(timeout 10 sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p 8022 100.127.72.24 'crontab -l 2>/dev/null' 2>/dev/null)
if [ -n "$PHONE_CRON" ]; then
    echo "  Phone crontab:"
    echo "$PHONE_CRON" | grep -v "^#" | grep -v "^$" | sed 's/^/    /'
else
    echo "  Phone SSH: FAILED"
fi
echo ""

# Grab logs
LOGS=$(journalctl -u pokemon-monitor-v2 --since "$WINDOW" --no-pager -o short-iso 2>/dev/null)

# === 5. NODRIVER SHOPS — PROBLEM DETECTION ===
echo "=== 5. NODRIVER SHOPS ==="
echo ""
printf "  %-16s %5s %5s %5s %5s %5s  %s\n" "SHOP" "SCANS" "ZEROS" "ERRS" "HEALS" "TOUTS" "LAST_STATUS"
for SHOP in empik mediaexpert tantis libristo boosterpoint strefamarzen bonito piwniczaki dragonus wilczek rgfk proshop; do
    SCANS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -c "produkt.*w [0-9]")
    ZEROS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -c "0 produktow")
    ERRS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "ERROR\|error:")
    HEALS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "heal")
    TOUTS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "timeout")
    LAST=$(echo "$LOGS" | grep "\[$SHOP\]" | tail -1 | sed 's/.*\] //' | head -c 60)
    printf "  %-16s %5d %5d %5d %5d %5d  %s\n" "$SHOP" "$SCANS" "$ZEROS" "$ERRS" "$HEALS" "$TOUTS" "$LAST"
done
echo ""
echo "  Stuck shops (>10 zeros, <3 scans) — last 3 lines each:"
for SHOP in bonito piwniczaki dragonus wilczek rgfk proshop; do
    ZEROS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -c "0 produktow")
    if [ "$ZEROS" -gt 5 ]; then
        echo "  --- $SHOP ($ZEROS zeros) ---"
        echo "$LOGS" | grep "\[$SHOP\]" | tail -3 | sed 's/^/    /'
    fi
done
echo ""

# === 6. ENGINE (tcgumisia proxy poller) ===
echo "=== 6. ENGINE ==="
ENGINE_POLLS=$(echo "$LOGS" | grep -c "\[tcgumisia-proxy\].*products")
ENGINE_SCANS=$(echo "$LOGS" | grep "\[tcgumisia\]" | grep -c "produktow w")
ENGINE_ERRS=$(echo "$LOGS" | grep "\[ENGINE\]" | grep -ci "error\|fail\|connect")
echo "  Polls: $ENGINE_POLLS | Scans reported: $ENGINE_SCANS | Errors: $ENGINE_ERRS"
echo "  Last 5 lines:"
echo "$LOGS" | grep -i "\[ENGINE\]" | tail -5 | sed 's/^/    /'
if [ "$ENGINE_ERRS" -gt 0 ]; then
    echo "  Error lines:"
    echo "$LOGS" | grep "\[ENGINE\]" | grep -iE "error|fail|connect" | tail -5 | sed 's/^/    /'
fi
echo ""

# === 7. FAST/SLOW PROBLEMS (shops with >20% errors or >5 consecutive zeros) ===
echo "=== 7. PROBLEM SHOPS (FAST/SLOW) ==="
echo ""
# Find shops with high error rates
echo "$LOGS" | awk '
/produkt.*w [0-9.]+s/ {
    n = split($0, p, "[")
    for (i=1;i<=n;i++) { sub(/\].*/, "", p[i])
        if (p[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && p[i] ~ /^[a-z]/) { shop=p[i]; break }
    }
    if (shop != "") scans[shop]++
}
/0 produktow/ {
    n = split($0, p, "[")
    for (i=1;i<=n;i++) { sub(/\].*/, "", p[i])
        if (p[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && p[i] ~ /^[a-z]/) { shop=p[i]; break }
    }
    if (shop != "") zeros[shop]++
}
/[Tt]imeout/ {
    n = split($0, p, "[")
    for (i=1;i<=n;i++) { sub(/\].*/, "", p[i])
        if (p[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && p[i] ~ /^[a-z]/) { shop=p[i]; break }
    }
    if (shop != "") touts[shop]++
}
END {
    printf "  %-20s %6s %6s %6s  %s\n", "SHOP", "SCANS", "ZEROS", "TOUTS", "NOTE"
    for (s in scans) {
        sc = scans[s]+0; z = zeros[s]+0; t = touts[s]+0
        total = sc + z + t
        if (total > 0 && (z > total*0.3 || t > total*0.2)) {
            note = ""
            if (z > total*0.5) note = "MOSTLY_EMPTY"
            else if (t > total*0.3) note = "TIMEOUT_HEAVY"
            else note = "DEGRADED"
            printf "  %-20s %6d %6d %6d  %s\n", s, sc, z, t, note
        }
    }
    # Also show shops with ONLY zeros (no scans)
    for (s in zeros) {
        if (!(s in scans) && zeros[s] > 3) {
            printf "  %-20s %6d %6d %6d  %s\n", s, 0, zeros[s], touts[s]+0, "ALL_EMPTY"
        }
    }
}' | sort -k3 -rn | head -20
echo ""

# === 8. CONSECUTIVE ERRORS / COOLDOWNS ===
echo "=== 8. COOLDOWNS + CONSECUTIVE ERRORS ==="
echo "$LOGS" | grep -i "cooldown\|consecutive error" | tail -15 | sed 's/^/  /'
echo ""

# === 9. HEALS (all shops) ===
echo "=== 9. HEALS ==="
HEAL_LINES=$(echo "$LOGS" | grep -i "heal #\|heal limit\|cooldown 30min\|Healing page")
if [ -n "$HEAL_LINES" ]; then
    echo "$HEAL_LINES" | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
        grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR)$' | \
        sort | uniq -c | sort -rn | head -15 | awk '{printf "  %3d x %s\n", $1, $2}'
    echo "  Total: $(echo "$HEAL_LINES" | wc -l)"
else
    echo "  (none)"
fi
echo ""

# === 10. TIMEOUTS PER SHOP ===
echo "=== 10. TIMEOUTS ==="
echo "$LOGS" | grep -i 'timeout' | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
    grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG)$' | \
    sort | uniq -c | sort -rn | head -15 | awk '{printf "  %3d x %s\n", $1, $2}'
TOTAL_TOUT=$(echo "$LOGS" | grep -ci 'timeout')
echo "  Total: $TOTAL_TOUT"
echo ""

# === 11. UNIQUE ERRORS ===
echo "=== 11. ERRORS (unique, last 20) ==="
echo "$LOGS" | grep -i '\[ERROR\]' | sed 's/^[^ ]* [^ ]* [^ ]* //' | sort -u | tail -20 | sed 's/^/  /'
echo ""

# === 12. DB EVENTS ===
echo "=== 12. DB ==="
DB_CMD="sudo -u postgres psql -d pokemonitor -t -A -c"
echo "  Products: $(timeout 5 $DB_CMD "SELECT count(*) FROM products;" 2>/dev/null || echo N/A)"
echo "  Events 1h: $(timeout 5 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '1 hour';" 2>/dev/null || echo N/A)"
echo "  Events 24h: $(timeout 5 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '24 hours';" 2>/dev/null || echo N/A)"
echo "  Breakdown (24h):"
timeout 5 $DB_CMD "SELECT event_type, count(*) FROM event_log WHERE ts > now() - interval '24 hours' GROUP BY event_type ORDER BY count DESC LIMIT 10;" 2>/dev/null | \
    awk -F'|' '{printf "    %-20s %s\n", $1, $2}' || echo "    (failed)"
echo ""

# === 13. CRON (VPS) ===
echo "=== 13. CRON ==="
crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | sed 's/^/  /'
echo ""

# === 14. PROCESS CRASHES ===
echo "=== 14. CRASHES/RESTARTS ==="
echo "$LOGS" | grep -iE "CRASH|Restarting|process.*died" | tail -10 | sed 's/^/  /'
MAIN_LINES=$(echo "$LOGS" | grep "\[MAIN\]")
if [ -n "$MAIN_LINES" ]; then
    echo "  MAIN supervisor:"
    echo "$MAIN_LINES" | tail -5 | sed 's/^/    /'
fi
echo ""

# === 15. PROXY WATCHDOG (last 30 lines) ===
echo "=== 15. PROXY WATCHDOG ==="
if [ -f /opt/pokemon-monitor-v2/proxy_watchdog.log ]; then
    tail -30 /opt/pokemon-monitor-v2/proxy_watchdog.log | sed 's/^/  /'
else
    echo "  (no log file)"
fi
echo ""

# === 16. SUMMARY ===
echo "=== 16. SUMMARY ==="
TOTAL_SCANS=$(echo "$LOGS" | grep -c "produkt.*w [0-9]")
TOTAL_POLLS=$(echo "$LOGS" | grep -c "\[tcgumisia-proxy\].*products")
TOTAL_ERRS=$(echo "$LOGS" | grep -c "\[ERROR\]")
TOTAL_TOUTS=$(echo "$LOGS" | grep -ci "timeout")
echo "  Window: last ${HOURS}h"
echo "  Scans: $TOTAL_SCANS | Engine polls: $TOTAL_POLLS | Errors: $TOTAL_ERRS | Timeouts: $TOTAL_TOUTS"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                     END DEEP DIAGNOSTIC                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Saved to /tmp/deep_diag.txt" >&2
