#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  POKEMON MONITOR v2 — FULL SYSTEM DIAGNOSTIC                ║
# ║  From last restart. Every shop. Every metric.               ║
# ║  Usage: bash infra/live_report.sh                           ║
# ║  Output: /tmp/live_report.txt                               ║
# ╚══════════════════════════════════════════════════════════════╝

exec > /tmp/live_report.txt 2>&1

# Determine window from last service restart
ACTIVE_TS=$(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
if [ -n "$ACTIVE_TS" ]; then
    SINCE_EPOCH=$(date -d "$ACTIVE_TS" +%s 2>/dev/null)
    NOW_EPOCH=$(date +%s)
    UPTIME_SECS=$((NOW_EPOCH - SINCE_EPOCH))
    UPTIME_H=$((UPTIME_SECS / 3600))
    UPTIME_M=$(( (UPTIME_SECS % 3600) / 60 ))
    WINDOW_SINCE="$ACTIVE_TS"
else
    WINDOW_SINCE="3 hours ago"
    UPTIME_H="?"
    UPTIME_M="?"
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  POKEMON MONITOR v2 — FULL DIAGNOSTIC                      ║"
echo "║  $(date '+%Y-%m-%d %H:%M:%S') | Since restart: ${UPTIME_H}h ${UPTIME_M}m       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
echo "=== 1. SYSTEM ==="
echo ""
echo "  Uptime:  $(uptime -p 2>/dev/null || uptime)"
echo "  Load:    $(cat /proc/loadavg | awk '{print "1m="$1" 5m="$2" 15m="$3}')"
echo "  Cores:   $(nproc)"
free -m | awk '/Mem:/ {printf "  RAM:     %dMB/%dMB used (%dMB free, %dMB available)\n", $3, $2, $4, $7}'
free -m | awk '/Swap:/ {printf "  Swap:    %dMB/%dMB\n", $3, $2}'
CHROME_COUNT=$(pgrep -c 'chrom' 2>/dev/null || echo 0)
CHROME_RAM=$(ps aux | grep -i 'chrom' | grep -v grep | awk '{sum+=$6} END {printf "%.0f", sum/1024}')
echo "  Chrome:  $CHROME_COUNT processes, ${CHROME_RAM}MB RAM"
echo ""

# ============================================================
echo "=== 2. SERVICE ==="
echo ""
MAIN_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID 2>/dev/null | cut -d= -f2)
echo "  Main PID: $MAIN_PID | Restart: $ACTIVE_TS | Running: ${UPTIME_H}h ${UPTIME_M}m"
echo ""
printf "  %-8s %-6s %-6s %-7s %-6s\n" "PID" "%CPU" "%MEM" "RSS_MB" "THR"
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    for PID in $MAIN_PID $(pgrep -P $MAIN_PID 2>/dev/null | head -6); do
        [ -d "/proc/$PID" ] || continue
        CPU=$(ps -p $PID -o %cpu= 2>/dev/null | tr -d ' ')
        MEM=$(ps -p $PID -o %mem= 2>/dev/null | tr -d ' ')
        RSS=$(($(ps -p $PID -o rss= 2>/dev/null | tr -d ' ') / 1024))
        THR=$(ps -p $PID -o nlwp= 2>/dev/null | tr -d ' ')
        printf "  %-8s %-6s %-6s %-7s %-6s\n" "$PID" "$CPU" "$MEM" "${RSS}M" "$THR"
    done
fi
echo ""

# ============================================================
echo "=== 3. PROXY ==="
echo ""
printf "  %-25s %-6s %-10s %s\n" "PATH" "CODE" "TIME" "IP"
RES=$(timeout 8 curl -x http://127.0.0.1:8888 -s -w "%{http_code} %{time_total}" --max-time 7 https://api.ipify.org 2>/dev/null)
IP=$(echo "$RES" | awk '{print $1}' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
CODE=$(echo "$RES" | awk '{print $(NF-1)}' | grep -oE '[0-9]{3}' | tail -1)
TIME=$(echo "$RES" | awk '{print $NF}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-" && IP="-"
printf "  %-25s %-6s %-10s %s\n" "HTTP Tunnel (8888)" "${CODE:-FAIL}" "${TIME:-?}s" "${IP:-?}"
RES=$(timeout 8 curl -x http://100.127.72.24:8888 -s -w "%{http_code} %{time_total}" --max-time 7 https://api.ipify.org 2>/dev/null)
IP=$(echo "$RES" | awk '{print $1}' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
CODE=$(echo "$RES" | awk '{print $(NF-1)}' | grep -oE '[0-9]{3}' | tail -1)
TIME=$(echo "$RES" | awk '{print $NF}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-" && IP="-"
printf "  %-25s %-6s %-10s %s\n" "Tailscale (100.x:8888)" "${CODE:-FAIL}" "${TIME:-?}s" "${IP:-?}"
RES=$(timeout 8 curl --socks5-hostname 127.0.0.1:1080 -s -w "%{http_code} %{time_total}" --max-time 7 https://api.ipify.org 2>/dev/null)
IP=$(echo "$RES" | awk '{print $1}' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
CODE=$(echo "$RES" | awk '{print $(NF-1)}' | grep -oE '[0-9]{3}' | tail -1)
TIME=$(echo "$RES" | awk '{print $NF}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-" && IP="-"
printf "  %-25s %-6s %-10s %s\n" "SOCKS5 (1080)" "${CODE:-FAIL}" "${TIME:-?}s" "${IP:-?}"
VPS_IP=$(timeout 5 curl -s --max-time 5 https://api.ipify.org 2>/dev/null)
printf "  %-25s %-6s %-10s %s\n" "VPS direct" "200" "-" "${VPS_IP:-?}"
echo ""

# ============================================================
echo "=== 4. PHONE (Mi 9T @ 100.127.72.24) ==="
echo ""
PING_AVG=$(timeout 5 ping -c 2 -W 2 100.127.72.24 2>/dev/null | tail -1 | awk -F'/' '{print $5}')
echo "  Ping: ${PING_AVG:-UNREACHABLE}ms"
PHONE_CRON=$(timeout 10 sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p 8022 100.127.72.24 'crontab -l 2>/dev/null' 2>/dev/null)
if [ -n "$PHONE_CRON" ]; then
    echo "  Crontab:"
    echo "$PHONE_CRON" | grep -v "^#" | grep -v "^$" | sed 's/^/    /'
else
    echo "  SSH: FAILED"
fi
echo ""

# ============================================================
# Grab ALL logs since restart (used by all subsequent sections)
LOGS=$(journalctl -u pokemon-monitor-v2 --since "$WINDOW_SINCE" --no-pager -o cat 2>/dev/null)

echo "=== 5. ALL SHOPS — FULL TABLE (since restart: ${UPTIME_H}h ${UPTIME_M}m) ==="
echo ""

if [ -z "$LOGS" ]; then
    echo "  (no logs)"
else
    echo "$LOGS" | awk '
    function get_shop(line,    n, parts, i, name) {
        n = split(line, parts, "[")
        name = ""
        for (i = 1; i <= n; i++) {
            sub(/\].*/, "", parts[i])
            if (parts[i] ~ /^ENGINE:/) { sub(/^ENGINE:/, "", parts[i]); name = parts[i]; break }
            if (parts[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && parts[i] ~ /^[a-zA-Z]/ && parts[i] ~ /[a-z]/) name = parts[i]
        }
        return name
    }
    function get_group(line,    n, parts, i) {
        n = split(line, parts, "[")
        for (i = 1; i <= n; i++) {
            sub(/\].*/, "", parts[i])
            if (parts[i] ~ /^ENGINE:/) return "ENGINE"
            if (parts[i] == "FAST" || parts[i] == "SLOW" || parts[i] == "NODRIVER" || parts[i] == "ENGINE") return parts[i]
        }
        return "?"
    }
    /produkt.*w [0-9.]+s/ {
        shop = get_shop($0); if (shop == "") next
        grp = get_group($0); shop_group[shop] = grp
        nw = split($0, words, " ")
        for (wi = 1; wi <= nw; wi++) if (words[wi] ~ /^produkt/) { last_products[shop] = words[wi-1]+0; break }
        t = -1
        for (wi = 1; wi <= nw; wi++) if (words[wi] == "w" && wi < nw) { tstr = words[wi+1]; gsub(/s$/, "", tstr); if (tstr ~ /^[0-9.]+$/) t = tstr+0.0; break }
        scan_count[shop]++
        if (t >= 0) { scan_time_sum[shop] += t }
    }
    /\[ENGINE\].*\[.*-proxy\].*products/ {
        shop = get_shop($0); if (shop == "") next
        shop_group[shop] = "ENGINE"
        if (match($0, /[0-9]+ products/)) { pstr = substr($0, RSTART, RLENGTH); split(pstr, pp, " "); last_products[shop] = pp[1]+0 }
        scan_count[shop]++
    }
    /0 produktow/ {
        shop = get_shop($0); if (shop != "" && shop !~ /[^a-zA-Z0-9_-]/) zeros[shop]++
    }
    /[Tt]imeout/ {
        shop = get_shop($0)
        if (shop != "" && shop !~ /[^a-zA-Z0-9_-]/) timeout_count[shop]++
        grp = get_group($0)
        if (shop != "" && shop !~ /[^a-zA-Z0-9_-]/ && grp != "?") shop_group[shop] = grp
    }
    /\[ERROR\]/ {
        shop = get_shop($0)
        if (shop != "" && shop !~ /[^a-zA-Z0-9_-]/) error_count[shop]++
        grp = get_group($0)
        if (shop != "" && shop !~ /[^a-zA-Z0-9_-]/ && grp != "?") shop_group[shop] = grp
    }
    END {
        for (s in scan_count) all_shops[s] = 1
        for (s in timeout_count) all_shops[s] = 1
        for (s in error_count) all_shops[s] = 1
        for (s in zeros) all_shops[s] = 1
        n = 0
        for (s in all_shops) { n++; names[n] = s; counts[n] = scan_count[s]+0 }
        for (i = 1; i <= n; i++) for (j = i+1; j <= n; j++) if (counts[j] > counts[i]) { tmp=counts[i]; counts[i]=counts[j]; counts[j]=tmp; tmp=names[i]; names[i]=names[j]; names[j]=tmp }
        for (i = 1; i <= n; i++) { s = names[i]; g = shop_group[s]; if (g == "") g = "?"; group_shops[g] = group_shops[g] " " i }
        split("FAST SLOW NODRIVER ENGINE ?", grp_order, " ")
        total_scans=0; total_tout=0; total_err=0; shops_ok=0; shops_sick=0; shops_dead=0
        for (gi = 1; gi <= 5; gi++) {
            g = grp_order[gi]; if (!(g in group_shops)) continue
            split(group_shops[g], idxs, " "); grp_count=0; grp_scans=0
            for (k in idxs) { if (idxs[k]=="") continue; grp_count++; grp_scans += scan_count[names[idxs[k]+0]]+0 }
            printf "\n  ━━━ %s (%d shops, %d scans) ━━━\n", g, grp_count, grp_scans
            printf "  %-22s %6s %5s %5s %5s %4s %4s  %s\n", "SHOP", "SCANS", "AVG", "PRODS", "ZEROS", "TOUT", "ERR", "STATUS"
            for (k = 1; k <= length(idxs); k++) {
                if (idxs[k]=="") continue; idx=idxs[k]+0; s=names[idx]
                sc=scan_count[s]+0; tc=timeout_count[s]+0; ec=error_count[s]+0; z=zeros[s]+0; prods=last_products[s]+0
                total_scans+=sc; total_tout+=tc; total_err+=ec
                avg_str = (sc>0) ? sprintf("%.0fs", scan_time_sum[s]/sc) : "-"
                if (sc==0 && z==0) { status="DEAD"; shops_dead++ }
                else if (sc==0 && z>0) { status="EMPTY"; shops_dead++ }
                else if (tc>0 && (tc*100/(sc+tc))>30) { status="SICK"; shops_sick++ }
                else if (ec>0 && (ec*100/sc)>20) { status="SICK"; shops_sick++ }
                else { status="OK"; shops_ok++ }
                printf "  %-22s %6d %5s %5d %5d %4d %4d  %s\n", s, sc, avg_str, prods, z, tc, ec, status
            }
        }
        printf "\n  ════════════════════════════════════════════════════\n"
        printf "  SCANNING: %d | SICK: %d | DEAD/EMPTY: %d\n", shops_ok, shops_sick, shops_dead
        printf "  Total scans: %d | Timeouts: %d | Errors: %d\n", total_scans, total_tout, total_err
        if (total_scans > 0) {
            printf "  Error rate: %.1f%% | Timeout rate: %.1f%%\n", (total_err*100/total_scans), (total_tout*100/total_scans)
        }
        # Write summary for section 12
        print total_scans > "/tmp/_lr_total_scans"
        print total_err > "/tmp/_lr_total_errors"
        print total_tout > "/tmp/_lr_total_timeouts"
        print shops_ok > "/tmp/_lr_shops_ok"
        print shops_dead + shops_sick > "/tmp/_lr_shops_broken"
    }
    '
fi
echo ""

# ============================================================
echo "=== 6. ENGINE (tcgumisia proxy poller) ==="
echo ""
ENGINE_POLLS=$(echo "$LOGS" | grep -c "\[tcgumisia-proxy\].*products")
ENGINE_SCANS=$(echo "$LOGS" | grep "\[tcgumisia\]" | grep -c "produktow w")
ENGINE_ERRS=$(echo "$LOGS" | grep "\[ENGINE\]" | grep -ci "error\|fail\|connect")
echo "  Polls: $ENGINE_POLLS | Scans: $ENGINE_SCANS | Errors: $ENGINE_ERRS"
if [ "$ENGINE_ERRS" -gt 0 ]; then
    echo "  Error lines:"
    echo "$LOGS" | grep "\[ENGINE\]" | grep -iE "error|fail|connect" | tail -5 | sed 's/^/    /'
fi
echo ""

# ============================================================
echo "=== 7. HEALS + COOLDOWNS ==="
echo ""
HEAL_LINES=$(echo "$LOGS" | grep -i "heal #\|heal limit\|cooldown 30min\|Healing page")
if [ -n "$HEAL_LINES" ]; then
    echo "  Heals per shop:"
    echo "$HEAL_LINES" | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
        grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR)$' | \
        sort | uniq -c | sort -rn | head -15 | awk '{printf "    %3d x %s\n", $1, $2}'
    echo "  Total heals: $(echo "$HEAL_LINES" | wc -l)"
else
    echo "  Heals: 0"
fi
echo ""
echo "  Cooldown entries (last 10):"
echo "$LOGS" | grep -i "cooldown\|consecutive error" | tail -10 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 8. TIMEOUTS (per shop) ==="
echo ""
echo "$LOGS" | grep -i 'timeout' | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
    grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG)$' | \
    sort | uniq -c | sort -rn | head -20 | awk '{printf "  %3d x %s\n", $1, $2}'
TOTAL_TOUT=$(echo "$LOGS" | grep -ci 'timeout')
echo "  Total: $TOTAL_TOUT"
echo ""

# ============================================================
echo "=== 9. ERRORS (unique, last 20) ==="
echo ""
echo "$LOGS" | grep -i '\[ERROR\]' | sed 's/^.*\] //' | sort -u | tail -20 | sed 's/^/  /'
echo ""

# ============================================================
echo "=== 10. DATABASE ==="
echo ""
DB_CMD="sudo -u postgres psql -d pokemonitor -t -A -c"
PROD_COUNT=$(timeout 5 $DB_CMD "SELECT count(*) FROM products;" 2>/dev/null)
EVENTS_1H=$(timeout 5 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '1 hour';" 2>/dev/null)
EVENTS_24H=$(timeout 5 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '24 hours';" 2>/dev/null)
echo "  Products: ${PROD_COUNT:-N/A} | Events 1h: ${EVENTS_1H:-N/A} | Events 24h: ${EVENTS_24H:-N/A}"
echo "  Breakdown (24h):"
timeout 5 $DB_CMD "SELECT event_type, count(*) FROM event_log WHERE ts > now() - interval '24 hours' GROUP BY event_type ORDER BY count DESC LIMIT 10;" 2>/dev/null | \
    awk -F'|' '{printf "    %-20s %s\n", $1, $2}' || echo "    (failed)"
echo ""

# ============================================================
echo "=== 11. NETWORK + DISK ==="
echo ""
printf "  %-12s %s\n" "PORT" "CONNECTIONS"
for PORT in 8191 8888 1080 5432; do
    COUNT=$(timeout 5 ss -tn 2>/dev/null | grep ":$PORT " | wc -l)
    printf "  %-12s %s\n" "$PORT" "$COUNT"
done
echo ""
echo "  Disk:"
df -h / 2>/dev/null | tail -1 | awk '{printf "    / : %s used / %s total (%s free, %s)\n", $3, $2, $4, $5}'
echo ""

# ============================================================
echo "=== 12. CRON ==="
echo ""
crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | sed 's/^/  /'
echo ""

# ============================================================
echo "=== 13. PROXY WATCHDOG (last 10 events) ==="
echo ""
if [ -f /opt/pokemon-monitor-v2/proxy_watchdog.log ]; then
    grep -v "^$" /opt/pokemon-monitor-v2/proxy_watchdog.log | tail -10 | sed 's/^/  /'
else
    echo "  (no log)"
fi
echo ""

# ============================================================
echo "=== 14. CRASHES / RESTARTS ==="
echo ""
CRASH_LINES=$(echo "$LOGS" | grep -iE "CRASH|Restarting|process.*died|killed|terminated")
if [ -n "$CRASH_LINES" ]; then
    echo "$CRASH_LINES" | tail -10 | sed 's/^/  /'
else
    echo "  (none)"
fi
echo ""

# ============================================================
echo "=== 15. CHROME TREND ==="
echo ""
PREV_COUNT=$(cat /tmp/_chrome_prev_count 2>/dev/null || echo "?")
echo "$CHROME_COUNT" > /tmp/_chrome_prev_count
echo "  Current: $CHROME_COUNT | Previous: $PREV_COUNT"
if [ "$PREV_COUNT" != "?" ] && [ "$CHROME_COUNT" -gt "$PREV_COUNT" ] 2>/dev/null; then
    echo "  Trend: +$((CHROME_COUNT - PREV_COUNT)) (GROWING ⚠️)"
elif [ "$PREV_COUNT" != "?" ] && [ "$CHROME_COUNT" -lt "$PREV_COUNT" ] 2>/dev/null; then
    echo "  Trend: -$((PREV_COUNT - CHROME_COUNT)) (shrinking ✅)"
else
    echo "  Trend: stable"
fi
echo ""

# ============================================================
echo "=== 17. AUTOBUY BOTS ==="
echo ""

# JC Torpedo Daemon
JC_STATUS=$(systemctl is-active jc-torpedo 2>/dev/null || echo "not-found")
if [ "$JC_STATUS" = "active" ]; then
    JC_PID=$(systemctl show jc-torpedo --property=MainPID 2>/dev/null | cut -d= -f2)
    JC_RAM=$(ps -p "$JC_PID" -o rss= 2>/dev/null | awk '{printf "%.0f", $1/1024}')
    JC_UPTIME=$(systemctl show jc-torpedo --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
    JC_LOG=$(journalctl -u jc-torpedo --since "1 hour ago" --no-pager 2>/dev/null)
    JC_POLLS=$(echo "$JC_LOG" | grep -c "available\|OOS\|error" 2>/dev/null || echo 0)
    JC_FIRES=$(echo "$JC_LOG" | grep -c "TORPEDO FIRE" 2>/dev/null || echo 0)
    JC_ORDERS=$(echo "$JC_LOG" | grep -c "✅ ORDER" 2>/dev/null || echo 0)
    JC_STAGED=$(echo "$JC_LOG" | grep -c "STAGED" 2>/dev/null || echo 0)
    JC_ERRORS=$(echo "$JC_LOG" | grep -c "ERROR\|Exception\|failed" 2>/dev/null || echo 0)
    JC_LAST_POLL=$(echo "$JC_LOG" | grep -oP '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' | tail -1)
    echo "  jc-torpedo:    ✅ ACTIVE (PID $JC_PID, ${JC_RAM}MB RAM)"
    echo "    Since:       $JC_UPTIME"
    echo "    Last log:    $JC_LAST_POLL"
    echo "    Polls/1h:    $JC_POLLS | Fires: $JC_FIRES | Orders: $JC_ORDERS"
    echo "    Staged:      $JC_STAGED | Errors: $JC_ERRORS"
    # Last few relevant log lines
    echo "    Recent:"
    echo "$JC_LOG" | grep -E "FIRE|ORDER|STAGED|RESTOCK|error|Exception" | tail -5 | sed 's/^/      /'
else
    echo "  jc-torpedo:    ❌ $JC_STATUS"
fi
echo ""

# ============================================================
echo "=== 18. SUMMARY ==="
echo ""
TOTAL_SCANS=$(cat /tmp/_lr_total_scans 2>/dev/null || echo 0)
TOTAL_ERRORS=$(cat /tmp/_lr_total_errors 2>/dev/null || echo 0)
TOTAL_TIMEOUTS=$(cat /tmp/_lr_total_timeouts 2>/dev/null || echo 0)
SHOPS_OK=$(cat /tmp/_lr_shops_ok 2>/dev/null || echo 0)
SHOPS_BROKEN=$(cat /tmp/_lr_shops_broken 2>/dev/null || echo 0)
if [ "$TOTAL_SCANS" -gt 0 ] 2>/dev/null; then
    ERR_RATE=$(awk "BEGIN {printf \"%.1f\", ($TOTAL_ERRORS / $TOTAL_SCANS) * 100}")
    TOUT_RATE=$(awk "BEGIN {printf \"%.1f\", ($TOTAL_TIMEOUTS / $TOTAL_SCANS) * 100}")
    SCANS_H=$(awk "BEGIN {printf \"%.0f\", $TOTAL_SCANS / (${UPTIME_H:-1} + ${UPTIME_M:-0}/60)}")
else
    ERR_RATE="0"; TOUT_RATE="0"; SCANS_H="0"
fi
echo "  Window: ${UPTIME_H}h ${UPTIME_M}m (since restart)"
echo "  Scans: $TOTAL_SCANS (~${SCANS_H}/h) | Errors: $TOTAL_ERRORS (${ERR_RATE}%) | Timeouts: $TOTAL_TIMEOUTS (${TOUT_RATE}%)"
echo "  Shops: $SHOPS_OK OK | $SHOPS_BROKEN SICK/DEAD"
echo "  Chrome: $CHROME_COUNT processes, ${CHROME_RAM}MB"
echo "  Load: $(cat /proc/loadavg | awk '{print $1}')"
echo ""

rm -f /tmp/_lr_total_scans /tmp/_lr_total_errors /tmp/_lr_total_timeouts /tmp/_lr_shops_ok /tmp/_lr_shops_broken

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                     END OF REPORT                           ║"
echo "║  Generated: $(date '+%Y-%m-%d %H:%M:%S')                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Report saved to /tmp/live_report.txt" >&2
