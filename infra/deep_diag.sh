#!/bin/bash
# Deep diagnostic v2 — mega detailed
exec > /tmp/deep_diag.txt 2>&1

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         DEEP DIAGNOSTIC $(date '+%Y-%m-%d %H:%M:%S')              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
echo "=== 1. PROCESY MONITORA — CPU / RAM / THREADS ==="
echo ""
MAIN_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID 2>/dev/null | cut -d= -f2)
echo "  Main PID: $MAIN_PID"
echo ""
printf "  %-12s %-8s %-6s %-6s %-6s %-8s %s\n" "PROCESS" "PID" "%CPU" "%MEM" "RSS_MB" "THREADS" "STARTED"
echo "  -----------------------------------------------------------------------"
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    # Get all child PIDs of monitor
    for PID in $MAIN_PID $(pgrep -P $MAIN_PID 2>/dev/null); do
        if [ -d "/proc/$PID" ]; then
            CPU=$(ps -p $PID -o %cpu= 2>/dev/null | tr -d ' ')
            MEM=$(ps -p $PID -o %mem= 2>/dev/null | tr -d ' ')
            RSS=$(ps -p $PID -o rss= 2>/dev/null | tr -d ' ')
            RSS_MB=$((${RSS:-0} / 1024))
            THR=$(ps -p $PID -o nlwp= 2>/dev/null | tr -d ' ')
            START=$(ps -p $PID -o lstart= 2>/dev/null | awk '{print $2,$3,$4}')
            CMD=$(ps -p $PID -o args= 2>/dev/null | head -c 60)
            # Identify process role
            ROLE="?"
            if [ "$PID" = "$MAIN_PID" ]; then ROLE="SUPERVISOR"
            elif echo "$CMD" | grep -q "patchright"; then ROLE="PATCHRIGHT"
            elif echo "$CMD" | grep -q "playwright"; then ROLE="PLAYWRIGHT"
            elif echo "$CMD" | grep -q "python"; then
                # Try to identify by thread name or proc name
                PNAME=$(cat /proc/$PID/comm 2>/dev/null)
                ROLE="PYTHON-$PID"
            fi
            printf "  %-12s %-8s %-6s %-6s %-6s %-8s %s\n" "$ROLE" "$PID" "$CPU" "$MEM" "${RSS_MB}M" "$THR" "$START"
        fi
    done
fi
echo ""
echo "  Chrome processes (summary):"
CHROME_PROCS=$(pgrep -c 'chrom' 2>/dev/null || echo 0)
CHROME_RSS=$(ps aux | grep -i 'chrom' | grep -v grep | awk '{sum+=$6} END {printf "%.0f", sum/1024}')
echo "    Count: $CHROME_PROCS"
echo "    Total RAM: ${CHROME_RSS}MB"
echo ""
echo "  System totals:"
echo "    Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')"
free -m | awk '/Mem:/ {printf "    RAM: %sMB used / %sMB total (%sMB free, %sMB available)\n", $3, $2, $4, $7}'
free -m | awk '/Swap:/ {printf "    Swap: %sMB used / %sMB total\n", $3, $2}'
echo ""

# ============================================================
echo "=== 2. NODRIVER STUCK SHOPS — PEŁNY TIMELINE ==="
echo ""

LOGS=$(journalctl -u pokemon-monitor-v2 --since "10 hours ago" --no-pager -o short-iso 2>/dev/null)

for SHOP in bonito piwniczaki dragonus wilczek proshop rgfk; do
    echo "━━━ $SHOP ━━━"
    TOTAL=$(echo "$LOGS" | grep -i "\[$SHOP\]" | wc -l)
    SCANS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep "produkt" | wc -l)
    TIMEOUTS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "timeout")
    ERRORS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "ERROR")
    HEALS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "heal")
    COOLDOWNS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "cooldown")
    echo "  Lines: $TOTAL | Scans: $SCANS | Timeouts: $TIMEOUTS | Errors: $ERRORS | Heals: $HEALS | Cooldowns: $COOLDOWNS"
    echo ""
    echo "  PEŁNA HISTORIA (wszystkie linie z timestampami):"
    echo "$LOGS" | grep -i "\[$SHOP\]" | sed 's/^/    /'
    echo ""
    echo ""
done

# ============================================================
echo "=== 3. MEDIAEXPERT — PEŁNA HISTORIA ==="
echo ""
TOTAL=$(echo "$LOGS" | grep "\[mediaexpert\]" | wc -l)
SCANS=$(echo "$LOGS" | grep "\[mediaexpert\]" | grep "produkt" | wc -l)
TIMEOUTS=$(echo "$LOGS" | grep "\[mediaexpert\]" | grep -ci "timeout")
ERRORS=$(echo "$LOGS" | grep "\[mediaexpert\]" | grep -ci "error")
echo "  Lines: $TOTAL | Scans: $SCANS | Timeouts: $TIMEOUTS | Errors: $ERRORS"
echo ""
echo "  Ostatnie 30 linii:"
echo "$LOGS" | grep "\[mediaexpert\]" | tail -30 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 4. SMYK — PEŁNA HISTORIA ==="
echo ""
TOTAL=$(echo "$LOGS" | grep "\[smyk\]" | wc -l)
SCANS=$(echo "$LOGS" | grep "\[smyk\]" | grep "produkt" | wc -l)
TIMEOUTS=$(echo "$LOGS" | grep "\[smyk\]" | grep -ci "timeout")
ERRORS=$(echo "$LOGS" | grep "\[smyk\]" | grep -ci "error")
echo "  Lines: $TOTAL | Scans: $SCANS | Timeouts: $TIMEOUTS | Errors: $ERRORS"
echo ""
echo "  Trigger/autobuy lines:"
echo "$LOGS" | grep -i "smyk" | grep -iE "trigger|autobuy|RESTOCK|NEW_PRODUCT|SOLD_OUT" | sed 's/^/    /'
echo ""
echo "  Ostatnie 20 linii:"
echo "$LOGS" | grep "\[smyk\]" | tail -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 5. ENGINE / PROXY POLLER — DLACZEGO DEAD? ==="
echo ""
echo "  Wszystkie linie ENGINE (pełny timeline):"
echo "$LOGS" | grep -iE "\[ENGINE\]|ENGINE:" | sed 's/^/    /'
echo ""
echo "  Proxy poller lines:"
echo "$LOGS" | grep -i "tcgumisia.proxy\|proxy_poller\|proxy.poller" | sed 's/^/    /'
echo ""
echo "  Proxy connection errors (8888):"
echo "$LOGS" | grep -i "127.0.0.1.*8888\|Connect call failed.*8888" | sed 's/^/    /'
echo ""
echo "  engine_runner.py — czy ma auto-restart? Sprawdźmy proces:"
ps aux | grep -i "engine\|poller" | grep -v grep | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 6. HEAL LOOP SHOPS — pokebeast, bastacentershop, archivebyx ==="
echo ""
for SHOP in pokebeast bastacentershop archivebyx; do
    echo "━━━ $SHOP ━━━"
    TOTAL=$(echo "$LOGS" | grep -i "\[$SHOP\]" | wc -l)
    SCANS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep "produkt" | wc -l)
    HEALS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "heal")
    echo "  Lines: $TOTAL | Scans: $SCANS | Heals: $HEALS"
    echo "  Ostatnie 20 linii:"
    echo "$LOGS" | grep -i "\[$SHOP\]" | tail -20 | sed 's/^/    /'
    echo ""
done

# ============================================================
echo "=== 7. MAGINARIUM + MONSTERIADA + AM76 (SLOW SICK/DEAD) ==="
echo ""
for SHOP in maginarium monsteriada am76; do
    echo "━━━ $SHOP ━━━"
    TOTAL=$(echo "$LOGS" | grep "\[$SHOP\]" | wc -l)
    SCANS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep "produkt" | wc -l)
    TIMEOUTS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "timeout")
    HEALS=$(echo "$LOGS" | grep "\[$SHOP\]" | grep -ci "heal")
    echo "  Lines: $TOTAL | Scans: $SCANS | Timeouts: $TIMEOUTS | Heals: $HEALS"
    echo "  Pełna historia:"
    echo "$LOGS" | grep "\[$SHOP\]" | sed 's/^/    /'
    echo ""
done

# ============================================================
echo "=== 8. NODRIVER PROCESS — STARTUP + WORKER STATUS ==="
echo ""
echo "  Startup sequence:"
echo "$LOGS" | grep "\[NODRIVER\]" | head -40 | sed 's/^/    /'
echo ""
echo "  Errors/warnings:"
echo "$LOGS" | grep "\[NODRIVER\]" | grep -iE "error|fail|skip|crash|NO scan_with_page" | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 9. CONSECUTIVE ERRORS + COOLDOWNS (FULL) ==="
echo ""
echo "  Wszystkie cooldown entries z timestampami:"
echo "$LOGS" | grep -i "cooldown\|consecutive error" | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 10. PROXY WATCHDOG LOG (ostatnie 100 linii) ==="
echo ""
if [ -f /opt/pokemon-monitor-v2/proxy_watchdog.log ]; then
    tail -100 /opt/pokemon-monitor-v2/proxy_watchdog.log | sed 's/^/    /'
else
    echo "    (file not found)"
fi
echo ""

# ============================================================
echo "=== 11. PROXY STATUS TERAZ ==="
echo ""
echo -n "  HTTP tunnel (8888): "
timeout 5 curl -x http://127.0.0.1:8888 -s -w "HTTP %{http_code} in %{time_total}s — IP: " --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo -n "  Tailscale direct: "
timeout 5 curl -x http://100.127.72.24:8888 -s -w "HTTP %{http_code} in %{time_total}s — IP: " --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo -n "  SOCKS5 (1080): "
timeout 5 curl --socks5-hostname 127.0.0.1:1080 -s -w "HTTP %{http_code} in %{time_total}s — IP: " --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo -n "  VPS direct: "
timeout 5 curl -s --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo ""

# ============================================================
echo "=== 12. PROCESS CRASHES + SUPERVISOR ==="
echo ""
echo "  MAIN supervisor (all lines):"
echo "$LOGS" | grep "\[MAIN\]" | sed 's/^/    /'
echo ""
echo "  Crash/restart lines:"
echo "$LOGS" | grep -iE "CRASH|restart|Restarting|died|killed|terminated" | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 13. SLOW PROCESS — CF BRIDGE STATUS ==="
echo ""
echo "  CF Bridge lines:"
echo "$LOGS" | grep -i "CF Bridge\|cf_bridge\|:8191" | head -20 | sed 's/^/    /'
echo ""
echo "  FlareSolverr errors:"
echo "$LOGS" | grep -i "FlareSolverr" | grep -i "error\|fail\|challenge" | tail -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 14. OPEN FILE DESCRIPTORS (potential leak) ==="
echo ""
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    for PID in $MAIN_PID $(pgrep -P $MAIN_PID 2>/dev/null); do
        if [ -d "/proc/$PID" ]; then
            FD_COUNT=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
            printf "    PID %-8s FDs: %s\n" "$PID" "$FD_COUNT"
        fi
    done
fi
echo ""

# ============================================================
echo "=== 15. NETWORK CONNECTIONS PER PROCESS ==="
echo ""
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    for PID in $(pgrep -P $MAIN_PID 2>/dev/null); do
        if [ -d "/proc/$PID" ]; then
            CONNS=$(ss -tnp 2>/dev/null | grep "pid=$PID" | wc -l)
            printf "    PID %-8s connections: %s\n" "$PID" "$CONNS"
        fi
    done
fi
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   END DEEP DIAGNOSTIC                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Saved to /tmp/deep_diag.txt" >&2
