#!/bin/bash
# FIX: Load too high — kill FlareSolverr, remove cron, clean processes
# Run: bash infra/fix_load.sh

set -e
echo "=== FIX LOAD — $(date) ==="

# 1. Stop FlareSolverr Docker permanently
echo "--- Stopping FlareSolverr Docker ---"
docker stop flaresolverr 2>/dev/null && echo "  Stopped" || echo "  Already stopped"
docker rm flaresolverr 2>/dev/null && echo "  Removed container" || echo "  No container to remove"

# 2. Remove FlareSolverr from crontab
echo "--- Removing FlareSolverr from crontab ---"
crontab -l 2>/dev/null | grep -v "flaresolverr" > /tmp/cron_clean.txt
crontab /tmp/cron_clean.txt
echo "  Done. New crontab:"
crontab -l

# 3. Restart monitor (picks up new code with dead shops disabled)
echo "--- Restarting monitor ---"
cd /opt/pokemon-monitor-v2
./venv/bin/python3 -c "import main" && echo "  Import OK" || { echo "  IMPORT FAILED! NOT RESTARTING!"; exit 1; }
sudo systemctl restart pokemon-monitor-v2
echo "  Restarted"

# 4. Wait and check
echo "--- Waiting 30s for startup ---"
sleep 30
echo "Load: $(cat /proc/loadavg)"
echo "Chrome: $(pgrep -c chrome 2>/dev/null || echo 0) processes"
echo "RAM free: $(free -m | awk '/Mem:/ {print $4}') MB"
echo "Monitor status: $(systemctl is-active pokemon-monitor-v2)"

echo ""
echo "=== DONE ==="
