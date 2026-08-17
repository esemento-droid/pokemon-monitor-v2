#!/bin/bash
# Deploy stability + speed fixes + restart monitor
# Run as: sudo bash infra/deploy_stability.sh
set -e

echo "=== STABILITY DEPLOY $(date) ==="

# Test import (catch syntax errors before restart)
echo "--- Testing import ---"
cd /opt/pokemon-monitor-v2
./venv/bin/python3 -c "import main; print('main.py OK')"
./venv/bin/python3 -c "import shops.piwniczaki; print('piwniczaki OK')"
./venv/bin/python3 -c "import shops.wilczek; print('wilczek OK')"
./venv/bin/python3 -c "import shops.dragonus; print('dragonus OK')"
./venv/bin/python3 -c "import shops.strefamarzen; print('strefamarzen OK')"
./venv/bin/python3 -c "import shops.rgfk; print('rgfk OK')"
./venv/bin/python3 -c "import session_warmer; print('session_warmer OK')"
echo "All imports OK!"
echo ""

# Deploy memory_guard v2
echo "--- Deploying memory_guard v2 ---"
chmod +x /opt/pokemon-monitor-v2/infra/memory_guard.sh
echo "  memory_guard.sh updated"

# Ensure cron points to correct location
GUARD_CRON="*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh"
CURRENT_CRON=$(crontab -u debian -l 2>/dev/null || true)
if ! echo "$CURRENT_CRON" | grep -qF "infra/memory_guard.sh"; then
    echo "$CURRENT_CRON" | grep -v "memory_guard" > /tmp/cron_tmp
    echo "$GUARD_CRON" >> /tmp/cron_tmp
    crontab -u debian /tmp/cron_tmp
    rm /tmp/cron_tmp
    echo "  Cron updated: memory_guard every 5 min"
else
    echo "  memory_guard cron OK"
fi
echo ""

# Restart monitor (loads new main.py + shops)
echo "--- Restarting monitor ---"
systemctl restart pokemon-monitor-v2
sleep 5
echo "  Status: $(systemctl is-active pokemon-monitor-v2)"
echo ""

echo "--- Final check ---"
free -h | head -2
echo "Chrome: $(pgrep -fc 'chromium|chrome-headless' 2>/dev/null || echo 0)"
echo "Monitor PID: $(systemctl show pokemon-monitor-v2 --property=MainPID --value)"
echo ""
echo "=== DEPLOY COMPLETE ==="
echo ""
echo "Changes deployed:"
echo "  - main.py: TIMEOUT_NODRIVER 300→120s, TIMEOUT_SLOW 180→120s"
echo "  - main.py: NODRIVER delay 90-180s → 30-60s (3x faster)"
echo "  - main.py: SLOW delay smart (proportional to scan time)"
echo "  - main.py: Dead shop progressive cooldown (5x→10min, 10x→30min)"
echo "  - main.py: nodriver kill uses full process group (no leaks)"
echo "  - main.py: SHOP_GROUP auto-classification (new shops need no main.py edit)"
echo "  - shops: try/finally browser.close() on all NODRIVER shops"
echo "  - session_warmer: 60s timeout per account"
echo "  - memory_guard v2: proactive Chrome limits (max 60)"
