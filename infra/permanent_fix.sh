#!/bin/bash
# PERMANENT RAM FIX — addresses root causes, not symptoms
# Run as: sudo bash infra/permanent_fix.sh
set -e

echo "=== PERMANENT FIX $(date) ==="
echo ""

# ============================================================
# 1. FlareSolverr with BROWSER_TIMEOUT + memory limit
#    Root cause: sessions never close → Chrome accumulates
# ============================================================
echo "--- 1. FlareSolverr: add BROWSER_TIMEOUT=60s, limit 512MB ---"
docker stop flaresolverr 2>/dev/null || true
docker rm flaresolverr 2>/dev/null || true
sleep 2

docker run -d \
    --name flaresolverr \
    --restart unless-stopped \
    --memory=512m \
    --memory-swap=768m \
    -e LOG_LEVEL=info \
    -e TZ=Europe/Warsaw \
    -e HEADLESS=true \
    -e BROWSER_TIMEOUT=60000 \
    -e MAX_TIMEOUT=120000 \
    -p 8191:8191 \
    ghcr.io/flaresolverr/flaresolverr:latest

echo "  BROWSER_TIMEOUT=60000 (closes idle sessions after 60s)"
echo "  MAX_TIMEOUT=120000 (max request time 120s)"
echo "  Memory: 512MB hard, 768MB with swap"
echo ""

# ============================================================
# 2. Fix session_warmer cron — add timeout 300s
#    Root cause: hangs forever on CF verification → Chrome leaks
# ============================================================
echo "--- 2. Fix session_warmer cron (timeout 300s) ---"
# Replace in debian's crontab
CURRENT=$(crontab -u debian -l 2>/dev/null)
if echo "$CURRENT" | grep -q "session_warmer.py"; then
    echo "$CURRENT" | sed 's|.*session_warmer.py.*|0 * * * * cd /opt/pokemon-monitor-v2 \&\& timeout 300 DISPLAY=:99 ./venv/bin/python3 session_warmer.py >> data/warmer.log 2>\&1|' | crontab -u debian -
    echo "  Fixed: added timeout 300"
else
    echo "  session_warmer not in cron (already removed?)"
fi
echo ""

# ============================================================
# 3. Check WARP usage — disable if not needed (saves 378MB)
# ============================================================
echo "--- 3. WARP-svc analysis ---"
# Check if any scraper or proxy_router references WARP
WARP_USED=$(grep -rn "warp\|1.1.1.1:2408\|socks5://.*40000" /opt/pokemon-monitor-v2/*.py /opt/pokemon-monitor-v2/shops/*.py 2>/dev/null | grep -v ".pyc" | head -5)
if [ -n "$WARP_USED" ]; then
    echo "  WARP IS USED in code:"
    echo "$WARP_USED"
    echo "  → Keeping active"
else
    echo "  WARP NOT referenced in any scraper/config"
    echo "  → Stopping warp-svc to save 378MB"
    systemctl stop warp-svc 2>/dev/null || true
    systemctl disable warp-svc 2>/dev/null || true
    echo "  → Disabled. Re-enable with: systemctl enable --now warp-svc"
fi
echo ""

# ============================================================
# 4. Verify crontab is clean
# ============================================================
echo "--- 4. Final debian crontab ---"
crontab -u debian -l 2>/dev/null
echo ""

# ============================================================
# 5. Final RAM check
# ============================================================
echo "--- 5. RAM status ---"
free -h
echo ""
echo "Chrome processes: $(ps aux | grep chromium | grep -v grep | wc -l)"
echo "Docker memory:"
docker stats --no-stream --format "  {{.Name}}: {{.MemUsage}}" 2>/dev/null
echo ""

echo "=== PERMANENT FIX COMPLETE ==="
echo ""
echo "WHAT WAS DONE:"
echo "  1. FlareSolverr: BROWSER_TIMEOUT=60s (kills idle Chrome sessions)"
echo "  2. session_warmer: timeout 300s (never hangs forever)"
echo "  3. WARP: disabled if unused (saves 378MB)"
echo "  4. memory_guard cron: already active (from ram_fix.sh)"
echo "  5. Swap 2GB: already active (from ram_fix.sh)"
echo ""
echo "WHY IT WON'T COME BACK:"
echo "  - FlareSolverr sessions auto-close after 60s idle"
echo "  - session_warmer force-killed after 5min"
echo "  - memory_guard kills zombies every 5min"
echo "  - Swap gives 2GB buffer before OOM"
echo "  - If RAM < 200MB → memory_guard restarts FlareSolverr"
