#!/bin/bash
# Deep diagnostic — investigate stuck/dead shops, proxy poller, heal loops
# Usage: bash infra/deep_diag.sh
exec > /tmp/deep_diag.txt 2>&1

echo "=== DEEP DIAGNOSTIC $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

LOGS=$(journalctl -u pokemon-monitor-v2 --since "10 hours ago" --no-pager -o cat 2>/dev/null)

# ============================================================
echo "=== 1. NODRIVER DEAD/STUCK: bonito, piwniczaki, dragonus, wilczek ==="
echo ""
for SHOP in bonito piwniczaki dragonus wilczek; do
    echo "--- $SHOP ---"
    echo "  All log lines (last 10h):"
    echo "$LOGS" | grep -i "\[$SHOP\]" | wc -l | xargs -I{} echo "    Total lines: {}"
    echo "  Successful scans:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep "produkt" | wc -l | xargs -I{} echo "    Count: {}"
    echo "  Errors:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep -iE "ERROR|error|fail|crash" | tail -5 | sed 's/^/    /'
    echo "  Timeouts:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep -i "timeout\|TIMEOUT" | wc -l | xargs -I{} echo "    Count: {}"
    echo "  Heals/cooldowns:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep -i "heal\|cooldown" | tail -5 | sed 's/^/    /'
    echo "  First log line:"
    echo "$LOGS" | grep "\[$SHOP\]" | head -1 | sed 's/^/    /'
    echo "  Last log line:"
    echo "$LOGS" | grep "\[$SHOP\]" | tail -1 | sed 's/^/    /'
    echo "  Timeline (first 10 + last 10 lines):"
    echo "$LOGS" | grep "\[$SHOP\]" | head -10 | sed 's/^/    /'
    echo "    ..."
    echo "$LOGS" | grep "\[$SHOP\]" | tail -10 | sed 's/^/    /'
    echo ""
done

# ============================================================
echo "=== 2. SMYK — full timeline ==="
echo ""
echo "  Total log lines:"
echo "$LOGS" | grep "\[smyk\]" | wc -l | xargs -I{} echo "    {}"
echo "  Successful scans:"
echo "$LOGS" | grep "\[smyk\]" | grep "produkt" | wc -l | xargs -I{} echo "    {}"
echo "  Errors/timeouts:"
echo "$LOGS" | grep "\[smyk\]" | grep -iE "error|timeout|fail" | tail -10 | sed 's/^/    /'
echo "  Last 5 scan lines:"
echo "$LOGS" | grep "\[smyk\]" | grep "produkt" | tail -5 | sed 's/^/    /'
echo "  Any trigger lines:"
echo "$LOGS" | grep -i "smyk" | grep -i "trigger\|autobuy\|RESTOCK\|NEW_PRODUCT" | tail -10 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 3. ENGINE / PROXY POLLER — why dead? ==="
echo ""
echo "  All ENGINE lines:"
echo "$LOGS" | grep -i "\[ENGINE\]\|ENGINE:" | wc -l | xargs -I{} echo "    Total lines: {}"
echo "  Errors:"
echo "$LOGS" | grep -i "\[ENGINE\]\|ENGINE:" | grep -iE "error\|fail\|connect\|dead\|crash" | tail -20 | sed 's/^/    /'
echo "  Timeline (first 10 + last 10):"
echo "$LOGS" | grep -i "\[ENGINE\]\|ENGINE:" | head -10 | sed 's/^/    /'
echo "    ..."
echo "$LOGS" | grep -i "\[ENGINE\]\|ENGINE:" | tail -10 | sed 's/^/    /'
echo ""
echo "  Proxy poller specific:"
echo "$LOGS" | grep -i "tcgumisia_proxy\|proxy_poller\|proxy poller" | tail -20 | sed 's/^/    /'
echo ""
echo "  Proxy errors (127.0.0.1:8888):"
echo "$LOGS" | grep "127.0.0.1.*8888\|8888.*fail\|8888.*error\|proxy.*connect" | head -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 4. HEAL LOOP SHOPS: bastacentershop, pokebeast, archivebyx, monsteriada ==="
echo ""
for SHOP in bastacentershop pokebeast archivebyx monsteriada; do
    echo "--- $SHOP ---"
    echo "  Total lines:"
    echo "$LOGS" | grep -i "\[$SHOP\]" | wc -l | xargs -I{} echo "    {}"
    echo "  Scans:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep "produkt" | wc -l | xargs -I{} echo "    {}"
    echo "  Heals:"
    echo "$LOGS" | grep "\[$SHOP\]" | grep -i "heal\|cooldown" | wc -l | xargs -I{} echo "    {}"
    echo "  Last 10 lines:"
    echo "$LOGS" | grep -i "\[$SHOP\]" | tail -10 | sed 's/^/    /'
    echo ""
done

# ============================================================
echo "=== 5. MAGINARIUM (SICK) ==="
echo ""
echo "  Total lines:"
echo "$LOGS" | grep "\[maginarium\]" | wc -l | xargs -I{} echo "    {}"
echo "  Scans:"
echo "$LOGS" | grep "\[maginarium\]" | grep "produkt" | wc -l | xargs -I{} echo "    {}"
echo "  Timeouts:"
echo "$LOGS" | grep "\[maginarium\]" | grep -i "timeout" | wc -l | xargs -I{} echo "    {}"
echo "  Heals/cooldowns:"
echo "$LOGS" | grep "\[maginarium\]" | grep -i "heal\|cooldown" | tail -10 | sed 's/^/    /'
echo "  Last 15 lines:"
echo "$LOGS" | grep "\[maginarium\]" | tail -15 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 6. NODRIVER PROCESS — startup + errors ==="
echo ""
echo "  NODRIVER startup lines:"
echo "$LOGS" | grep "\[NODRIVER\]" | head -30 | sed 's/^/    /'
echo ""
echo "  NODRIVER errors (last 20):"
echo "$LOGS" | grep "\[NODRIVER\]" | grep -iE "error\|fail\|crash\|skip" | tail -20 | sed 's/^/    /'
echo ""
echo "  Browser manager lines:"
echo "$LOGS" | grep -i "BROWSER_MGR\|browser_manager\|BrowserManager" | tail -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 7. PROXY WATCHDOG (last 30 min of proxy_watchdog.log) ==="
echo ""
if [ -f /opt/pokemon-monitor-v2/proxy_watchdog.log ]; then
    tail -50 /opt/pokemon-monitor-v2/proxy_watchdog.log | sed 's/^/    /'
else
    echo "    (file not found)"
fi
echo ""

# ============================================================
echo "=== 8. PROCESS CRASHES / RESTARTS ==="
echo ""
echo "  Process crash lines:"
echo "$LOGS" | grep -iE "CRASHED|Restarting|process.*died\|killed" | tail -20 | sed 's/^/    /'
echo ""
echo "  MAIN supervisor lines:"
echo "$LOGS" | grep "\[MAIN\]" | tail -10 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 9. CF_SOLVER / CF_BRIDGE errors ==="
echo ""
echo "  CF errors (last 20):"
echo "$LOGS" | grep -i "CF_SOLVER\|cf_bridge\|cf_solver" | grep -iE "error\|fail\|timeout\|ERR_PROXY" | tail -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 10. CONSECUTIVE ERRORS + COOLDOWNS (all shops) ==="
echo ""
echo "  Shops that hit cooldown:"
echo "$LOGS" | grep -i "cooldown\|consecutive errors" | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR)$' | sort | uniq -c | sort -rn | head -20 | awk '{printf "    %3d x %s\n", $1, $2}'
echo ""
echo "  Cooldown lines (last 20):"
echo "$LOGS" | grep -i "cooldown\|consecutive errors" | tail -20 | sed 's/^/    /'
echo ""

# ============================================================
echo "=== 11. CURRENT PROXY STATUS ==="
echo ""
echo "  HTTP tunnel test:"
timeout 5 curl -x http://127.0.0.1:8888 -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s" --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo "  Mobile IP:"
timeout 5 curl -x http://127.0.0.1:8888 -s --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo "  VPS IP:"
timeout 5 curl -s --max-time 5 https://api.ipify.org 2>/dev/null
echo ""
echo ""

echo "=== END DEEP DIAGNOSTIC ==="
echo "Saved to /tmp/deep_diag.txt" >&2
