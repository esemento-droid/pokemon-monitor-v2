#!/bin/bash
# Live system report - full diagnostics from last hour
# Usage: bash infra/live_report.sh
# Output: /tmp/live_report.txt

exec > /tmp/live_report.txt 2>&1

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            POKEMON MONITOR v2 - LIVE REPORT                 ║"
echo "║            $(date '+%Y-%m-%d %H:%M:%S')                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# === 1. SYSTEM ===
# ============================================================
echo "=== 1. SYSTEM ==="
echo ""
echo "Uptime:   $(uptime -p 2>/dev/null || uptime)"
echo "Load avg: $(cat /proc/loadavg 2>/dev/null | awk '{print "1min="$1" 5min="$2" 15min="$3}')"
echo "CPU cores: $(nproc 2>/dev/null || grep -c processor /proc/cpuinfo 2>/dev/null)"
echo ""
echo "RAM:"
free -h 2>/dev/null | grep -E "Mem|Swap" | awk '{printf "  %-6s total=%-8s used=%-8s free=%-8s\n", $1, $2, $3, $4}'
echo ""

# ============================================================
# === 2. PEAK CPU/RAM ===
# ============================================================
echo "=== 2. PEAK CPU/RAM ==="
echo ""
echo "Top 20 by CPU:"
printf "  %-8s %-6s %-6s %s\n" "PID" "%CPU" "%MEM" "COMMAND"
timeout 10 ps aux --sort=-%cpu 2>/dev/null | tail -n +2 | head -20 | awk '{printf "  %-8s %-6s %-6s %s\n", $2, $3, $4, $11}'
echo ""
echo "Top 20 by RAM:"
printf "  %-8s %-6s %-6s %s\n" "PID" "%CPU" "%MEM" "COMMAND"
timeout 10 ps aux --sort=-%mem 2>/dev/null | tail -n +2 | head -20 | awk '{printf "  %-8s %-6s %-6s %s\n", $2, $3, $4, $11}'
echo ""

# ============================================================
# === 3. MONITOR SERVICE ===
# ============================================================
echo "=== 3. MONITOR SERVICE ==="
echo ""
echo "Status:"
timeout 10 systemctl status pokemon-monitor-v2 --no-pager 2>&1 | head -15 | sed 's/^/  /'
echo ""
echo "PID tree:"
MAIN_PID=$(systemctl show pokemon-monitor-v2 --property=MainPID 2>/dev/null | cut -d= -f2)
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    timeout 10 pstree -p "$MAIN_PID" 2>/dev/null | head -20 | sed 's/^/  /'
else
    echo "  (service not running or PID unavailable)"
fi
echo ""
echo "Last restart: $(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)"
ACTIVE_SINCE=$(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestampMonotonic 2>/dev/null | cut -d= -f2)
ACTIVE_TS=$(systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
if [ -n "$ACTIVE_TS" ]; then
    SINCE_EPOCH=$(date -d "$ACTIVE_TS" +%s 2>/dev/null)
    NOW_EPOCH=$(date +%s)
    if [ -n "$SINCE_EPOCH" ]; then
        UPTIME_SECS=$((NOW_EPOCH - SINCE_EPOCH))
        UPTIME_H=$((UPTIME_SECS / 3600))
        UPTIME_M=$(( (UPTIME_SECS % 3600) / 60 ))
        echo "Running for: ${UPTIME_H}h ${UPTIME_M}m"
    fi
fi
echo ""

# ============================================================
# === 4. CHROME ===
# ============================================================
echo "=== 4. CHROME ==="
echo ""
CHROME_COUNT=$(pgrep -c 'chrom' 2>/dev/null)
[ -z "$CHROME_COUNT" ] && CHROME_COUNT=0
CHROME_RAM=$(ps aux 2>/dev/null | grep -i 'chrom' | grep -v grep | awk '{sum+=$6} END {if(sum>0) printf "%.0f", sum/1024; else print "0"}')
echo "Chrome/Chromium processes: $CHROME_COUNT"
echo "Total Chrome RAM: ${CHROME_RAM} MB"
echo ""

# Grab logs once (used by sections 4a, 4b, 5, 7, 8)
LOGS=$(journalctl -u pokemon-monitor-v2 --since "60 min ago" --no-pager -o cat 2>/dev/null)

# ============================================================
# === 4a. CHROME TREND ===
# ============================================================
echo "=== 4a. CHROME TREND ==="
echo ""
PREV_COUNT=$(cat /tmp/_chrome_prev_count 2>/dev/null || echo "?")
echo "$CHROME_COUNT" > /tmp/_chrome_prev_count
echo "  Current: $CHROME_COUNT processes"
echo "  Previous report: $PREV_COUNT processes"
if [ "$PREV_COUNT" != "?" ] && [ "$CHROME_COUNT" -gt "$PREV_COUNT" ] 2>/dev/null; then
    DIFF=$((CHROME_COUNT - PREV_COUNT))
    echo "  Trend: +$DIFF (GROWING)"
elif [ "$PREV_COUNT" != "?" ] && [ "$CHROME_COUNT" -lt "$PREV_COUNT" ] 2>/dev/null; then
    DIFF=$((PREV_COUNT - CHROME_COUNT))
    echo "  Trend: -$DIFF (shrinking)"
else
    echo "  Trend: stable (or first run)"
fi
echo ""

# ============================================================
# === 4b. NODRIVER HEALS (from logs) ===
# ============================================================
echo "=== 4b. NODRIVER HEALS (from logs) ==="
echo ""
if [ -n "$LOGS" ]; then
    echo "$LOGS" | grep -i "heal #\|heal limit\|cooldown 30min\|Healing page" | \
        grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
        grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR)$' | \
        sort | uniq -c | sort -rn | head -10 | \
        awk '{printf "  %3d x %s\n", $1, $2}'
    TOTAL_HEALS=$(echo "$LOGS" | grep -ci "heal #\|Healing page")
    echo ""
    echo "  Total heals last hour: $TOTAL_HEALS"
    # Show cooldowns
    COOLDOWNS=$(echo "$LOGS" | grep -c "cooldown 30min\|heal limit")
    echo "  Shops in cooldown: $COOLDOWNS"
else
    echo "  (no logs)"
fi
echo ""

# ============================================================
# === 5. LOGI OSTATNIA GODZINA - PER SCRAPER (grouped) ===
# ============================================================
echo "=== 5. SHOPY — SKANY/H (grupowane FAST / SLOW / NODRIVER) ==="
echo ""

if [ -z "$LOGS" ]; then
    echo "  (no logs from last hour)"
else
    # Parse per-shop stats, detect process group from log prefix, output grouped
    echo "$LOGS" | awk '
    function get_shop(line,    n, parts, i, name) {
        n = split(line, parts, "[")
        name = ""
        for (i = 1; i <= n; i++) {
            sub(/\].*/, "", parts[i])
            if (parts[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && parts[i] ~ /^[a-zA-Z]/ && parts[i] ~ /[a-z]/) {
                name = parts[i]
            }
        }
        return name
    }

    function get_group(line,    n, parts, i) {
        n = split(line, parts, "[")
        for (i = 1; i <= n; i++) {
            sub(/\].*/, "", parts[i])
            if (parts[i] == "FAST" || parts[i] == "SLOW" || parts[i] == "NODRIVER" || parts[i] == "ENGINE") {
                return parts[i]
            }
        }
        return "?"
    }

    /produkt.*w [0-9.]+s/ {
        shop = get_shop($0)
        if (shop == "") next
        grp = get_group($0)
        shop_group[shop] = grp

        nw = split($0, words, " ")
        for (wi = 1; wi <= nw; wi++) {
            if (words[wi] ~ /^produkt/) {
                last_products[shop] = words[wi-1] + 0
                break
            }
        }
        t = -1
        for (wi = 1; wi <= nw; wi++) {
            if (words[wi] == "w" && wi < nw) {
                tstr = words[wi+1]
                gsub(/s$/, "", tstr)
                if (tstr ~ /^[0-9.]+$/) t = tstr + 0.0
                break
            }
        }
        scan_count[shop]++
        if (t >= 0) {
            scan_time_sum[shop] += t
            if (!(shop in scan_time_min) || t < scan_time_min[shop]) scan_time_min[shop] = t
            if (!(shop in scan_time_max) || t > scan_time_max[shop]) scan_time_max[shop] = t
        }
    }

    /[Tt]imeout/ {
        shop = get_shop($0)
        if (shop != "") timeout_count[shop]++
        grp = get_group($0)
        if (shop != "" && grp != "?") shop_group[shop] = grp
    }

    /\[ERROR\]/ {
        shop = get_shop($0)
        if (shop != "") error_count[shop]++
        grp = get_group($0)
        if (shop != "" && grp != "?") shop_group[shop] = grp
    }

    END {
        for (s in scan_count) all_shops[s] = 1
        for (s in timeout_count) all_shops[s] = 1
        for (s in error_count) all_shops[s] = 1

        # Classify shops: DEAD (0 scans), SICK (>30% timeout), OK
        total_scans = 0; total_timeouts = 0; total_errors = 0
        shops_scanning = 0; shops_dead = 0; shops_sick = 0

        # Collect into arrays per group
        n = 0
        for (s in all_shops) {
            n++
            names[n] = s
            counts[n] = scan_count[s] + 0
        }
        # Sort by scan count desc
        for (i = 1; i <= n; i++) {
            for (j = i + 1; j <= n; j++) {
                if (counts[j] > counts[i]) {
                    tmp = counts[i]; counts[i] = counts[j]; counts[j] = tmp
                    tmp = names[i]; names[i] = names[j]; names[j] = tmp
                }
            }
        }

        # Print grouped by process
        # Pass 1: collect groups
        for (i = 1; i <= n; i++) {
            s = names[i]
            g = shop_group[s]
            if (g == "") g = "?"
            group_shops[g] = group_shops[g] " " i
        }

        # Print order: FAST, SLOW, NODRIVER, ENGINE, ?
        split("FAST SLOW NODRIVER ENGINE ?", grp_order, " ")

        for (gi = 1; gi <= 5; gi++) {
            g = grp_order[gi]
            if (!(g in group_shops)) continue

            # Count shops in group
            split(group_shops[g], idxs, " ")
            grp_count = 0
            grp_scans = 0
            for (k in idxs) {
                if (idxs[k] == "") continue
                grp_count++
                grp_scans += scan_count[names[idxs[k]+0]] + 0
            }

            printf "\n  ━━━ %s (%d shops, %d scans/h) ━━━\n", g, grp_count, grp_scans
            printf "  %-22s %5s %6s %5s %4s %4s  %s\n", "SHOP", "SCANS", "AVG", "PRODS", "TOUT", "ERR", "STATUS"

            split(group_shops[g], idxs, " ")
            for (k = 1; k <= length(idxs); k++) {
                if (idxs[k] == "") continue
                idx = idxs[k] + 0
                s = names[idx]
                sc = scan_count[s] + 0
                tc = timeout_count[s] + 0
                ec = error_count[s] + 0
                prods = last_products[s] + 0
                total_scans += sc
                total_timeouts += tc
                total_errors += ec

                if (sc > 0) {
                    avg_str = sprintf("%.0fs", scan_time_sum[s] / sc)
                } else {
                    avg_str = "-"
                }

                # Status classification:
                # DEAD = 0 scans
                # SICK = >30% timeouts or >20% errors
                # OK = scanning fine
                if (sc == 0) {
                    if (ec > 0) status = "DEAD"
                    else if (tc > 0) status = "DEAD"
                    else status = "DEAD"
                    shops_dead++
                } else if (tc > 0 && (tc * 100 / (sc + tc)) > 30) {
                    status = "SICK"
                    shops_sick++
                } else if (ec > 0 && (ec * 100 / sc) > 20) {
                    status = "SICK"
                    shops_sick++
                } else {
                    status = "OK"
                    shops_scanning++
                }

                printf "  %-22s %5d %6s %5d %4d %4d  %s\n", s, sc, avg_str, prods, tc, ec, status
            }
        }

        printf "\n  ════════════════════════════════════════════════════\n"
        printf "  SCANNING: %d | SICK (>30%% tout): %d | DEAD (0 scans): %d\n", shops_scanning, shops_sick, shops_dead
        printf "  Total: %d scans/h | %d timeouts | %d errors\n", total_scans, total_timeouts, total_errors

        # Write summary values to temp file
        print total_scans > "/tmp/_lr_total_scans"
        print total_errors > "/tmp/_lr_total_errors"
        print total_timeouts > "/tmp/_lr_total_timeouts"
        print shops_scanning > "/tmp/_lr_shops_ok"
        print shops_dead + shops_sick > "/tmp/_lr_shops_broken"
    }
    '
fi
echo ""

# ============================================================
# === 6. PROXY STABILITY ===
# ============================================================
echo "=== 6. PROXY STABILITY ==="
echo ""
printf "  %-25s %-8s %s\n" "PATH" "STATUS" "TIME"
printf "  %-25s %-8s %s\n" "----" "------" "----"

# HTTP Tunnel
RES=$(timeout 10 curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 8 --max-time 10 https://api.ipify.org 2>/dev/null)
CODE=$(echo "$RES" | awk '{print $1}')
TIME=$(echo "$RES" | awk '{print $2}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-"
[ "$CODE" = "000" ] && CODE="FAIL"
printf "  %-25s %-8s %ss\n" "HTTP Tunnel (8888)" "$CODE" "$TIME"

# Tailscale
RES=$(timeout 10 curl -x http://100.127.72.24:8888 -s -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 8 --max-time 10 https://api.ipify.org 2>/dev/null)
CODE=$(echo "$RES" | awk '{print $1}')
TIME=$(echo "$RES" | awk '{print $2}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-"
[ "$CODE" = "000" ] && CODE="FAIL"
printf "  %-25s %-8s %ss\n" "Tailscale (100.x:8888)" "$CODE" "$TIME"

# SOCKS5
RES=$(timeout 10 curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 8 --max-time 10 https://api.ipify.org 2>/dev/null)
CODE=$(echo "$RES" | awk '{print $1}')
TIME=$(echo "$RES" | awk '{print $2}')
[ -z "$CODE" ] && CODE="FAIL" && TIME="-"
[ "$CODE" = "000" ] && CODE="FAIL"
printf "  %-25s %-8s %ss\n" "SOCKS5 (1080)" "$CODE" "$TIME"
echo ""

# ============================================================
# === 7. BLEDY (ostatnie 20 unikalnych) ===
# ============================================================
echo "=== 7. BLEDY (ostatnie 20 unikalnych) ==="
echo ""
if [ -n "$LOGS" ]; then
    echo "$LOGS" | grep -iE '\[ERROR\]|error|exception|traceback|fail' | \
        grep -v "^$" | \
        sed 's/^.*\] //' | \
        sort -u | \
        tail -20 | \
        nl -w3 -s'. ' | \
        sed 's/^/  /'
else
    echo "  (no logs)"
fi
echo ""

# ============================================================
# === 8. TIMEOUTY ===
# ============================================================
echo "=== 8. TIMEOUTY (ktore shopy i ile razy) ==="
echo ""
if [ -n "$LOGS" ]; then
    echo "$LOGS" | grep -i 'timeout' | \
        grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | \
        grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG)$' | \
        sort | uniq -c | sort -rn | head -20 | \
        awk '{printf "  %3d x %s\n", $1, $2}'
    TOTAL_TOUT=$(echo "$LOGS" | grep -ci 'timeout')
    echo ""
    echo "  Total timeouts last hour: $TOTAL_TOUT"
else
    echo "  (no logs)"
fi
echo ""

# ============================================================
# === 9. DISK ===
# ============================================================
echo "=== 9. DISK ==="
echo ""
echo "Filesystem usage:"
df -h / /opt 2>/dev/null | sort -u | sed 's/^/  /'
echo ""
echo "Monitor data dir:"
timeout 10 du -sh /opt/pokemon-monitor-v2/data/ 2>/dev/null | sed 's/^/  /' || echo "  (not accessible)"
echo "Monitor logs:"
timeout 10 du -sh /opt/pokemon-monitor-v2/*.log 2>/dev/null | sed 's/^/  /' || echo "  (no log files)"
timeout 10 du -sh /opt/pokemon-monitor-v2/data/*.log 2>/dev/null | sed 's/^/  /' || echo "  (no data log files)"
echo ""

# ============================================================
# === 10. NETWORK ===
# ============================================================
echo "=== 10. NETWORK (open connections) ==="
echo ""
printf "  %-12s %s\n" "PORT" "CONNECTIONS"
printf "  %-12s %s\n" "----" "-----------"
for PORT in 8191 8888 1080 5432; do
    COUNT=$(timeout 10 ss -tn 2>/dev/null | grep ":$PORT " | wc -l)
    printf "  %-12s %s\n" "$PORT" "$COUNT"
done
echo ""
echo "Listening services on key ports:"
timeout 10 ss -tlnp 2>/dev/null | grep -E ':(8191|8888|1080|5432) ' | sed 's/^/  /'
echo ""

# ============================================================
# === 11. CRON ===
# ============================================================
echo "=== 11. CRON JOBS ==="
echo ""
echo "Root crontab:"
crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | sed 's/^/  /' || echo "  (empty)"
echo ""
echo "System cron.d:"
ls /etc/cron.d/ 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo ""

# ============================================================
# === 12. DB ===
# ============================================================
echo "=== 12. DATABASE ==="
echo ""
DB_CMD="sudo -u postgres psql -d pokemonitor -t -A -c"

PROD_COUNT=$(timeout 10 $DB_CMD "SELECT count(*) FROM products;" 2>/dev/null)
EVENTS_1H=$(timeout 10 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '1 hour';" 2>/dev/null)
EVENTS_24H=$(timeout 10 $DB_CMD "SELECT count(*) FROM event_log WHERE ts > now() - interval '24 hours';" 2>/dev/null)

echo "  Products total:       ${PROD_COUNT:-N/A}"
echo "  Events last 1h:       ${EVENTS_1H:-N/A}"
echo "  Events last 24h:      ${EVENTS_24H:-N/A}"
echo ""
echo "  Event breakdown (last 1h):"
timeout 10 $DB_CMD "SELECT event_type, count(*) as cnt FROM event_log WHERE ts > now() - interval '1 hour' GROUP BY event_type ORDER BY cnt DESC LIMIT 10;" 2>/dev/null | \
    awk -F'|' '{printf "    %-20s %s\n", $1, $2}' || echo "    (query failed)"
echo ""

# ============================================================
# === 13. PHONE ===
# ============================================================
echo "=== 13. PHONE (Mi 9T @ 100.127.72.24) ==="
echo ""
echo -n "  Ping: "
PING_RES=$(timeout 10 ping -c 3 -W 3 100.127.72.24 2>/dev/null | tail -1)
if [ -n "$PING_RES" ]; then
    echo "$PING_RES"
else
    echo "UNREACHABLE"
fi
echo -n "  SSH check: "
timeout 10 sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p 8022 100.127.72.24 'echo OK' 2>/dev/null
if [ $? -ne 0 ]; then
    echo "FAILED"
fi
echo ""

# ============================================================
# === 14. PODSUMOWANIE ===
# ============================================================
echo "=== 14. PODSUMOWANIE ==="
echo ""

# Read summary values from temp files (written by awk)
TOTAL_SCANS=$(cat /tmp/_lr_total_scans 2>/dev/null || echo 0)
TOTAL_ERRORS=$(cat /tmp/_lr_total_errors 2>/dev/null || echo 0)
TOTAL_TIMEOUTS=$(cat /tmp/_lr_total_timeouts 2>/dev/null || echo 0)
SHOPS_OK=$(cat /tmp/_lr_shops_ok 2>/dev/null || echo 0)
SHOPS_BROKEN=$(cat /tmp/_lr_shops_broken 2>/dev/null || echo 0)

# Calculate percentages
if [ "$TOTAL_SCANS" -gt 0 ] 2>/dev/null; then
    ERROR_RATE=$(awk "BEGIN {printf \"%.1f\", ($TOTAL_ERRORS / $TOTAL_SCANS) * 100}")
    TIMEOUT_RATE=$(awk "BEGIN {printf \"%.1f\", ($TOTAL_TIMEOUTS / $TOTAL_SCANS) * 100}")
else
    ERROR_RATE="0.0"
    TIMEOUT_RATE="0.0"
    TOTAL_SCANS=0
fi

echo "  $TOTAL_SCANS scans/h | ${ERROR_RATE}% errors | ${TIMEOUT_RATE}% timeouts"
echo "  SCANNING: $SHOPS_OK | SICK+DEAD: $SHOPS_BROKEN"
echo ""

# Cleanup temp files
rm -f /tmp/_lr_total_scans /tmp/_lr_total_errors /tmp/_lr_total_timeouts /tmp/_lr_shops_ok /tmp/_lr_shops_broken

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                     END OF REPORT                           ║"
echo "║  Generated: $(date '+%Y-%m-%d %H:%M:%S')                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"

echo ""
echo "Report saved to /tmp/live_report.txt" >&2
