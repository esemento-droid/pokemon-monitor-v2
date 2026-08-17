#!/bin/bash
# Deploy stability fixes + restart monitor
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
cp infra/memory_guard.sh /opt/pokemon-monitor-v2/infra/memory_guard.sh
chmod +x /opt/pokemon-monitor-v2/infra/memory_guard.sh
echo "  memory_guard.sh updated"

# Ensure cron points to new location
CRON_LINE="*/5 * * * * /opt/pokemon-monitor-v2/infra/memory_guard.sh"
if ! crontab -u debian -l 2>/dev/null | grep -qF "infra/memory_guard.sh"; then
    # Remove old memory_guard cron if exists
    crontab -u debian -l 2>/dev/null | grep -v "memory_guard" | crontab -u debian -
    (crontab -u debian -l 2>/dev/null; echo "$CRON_LINE") | crontab -u debian -
    echo "  Cron updated to use infra/memory_guard.sh"
fi
echo ""

# Restart monitor (loads new main.py + shops)
echo "--- Restarting monitor ---"
systemctl restart pokemon-monitor-v2
sleep 3
echo "  Status: $(systemctl is-active pokemon-monitor-v2)"
echo ""

echo "--- Final check ---"
free -h | head -2
echo "Chrome: $(pgrep -fc 'chromium|chrome-headless' 2>/dev/null || echo 0)"
echo ""
echo "=== DEPLOY COMPLETE ==="
