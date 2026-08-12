#!/bin/bash
# ================================================================
# DEPLOY VPS INFRASTRUCTURE
# Run: cd /opt/pokemon-monitor-v2 && bash infra/deploy_vps.sh
# ================================================================
set -e
BASE="/opt/pokemon-monitor-v2"
LOG="$BASE/data/deploy.log"
mkdir -p "$BASE/data"

log() { echo "$(date '+%H:%M:%S') $1" | tee -a "$LOG"; }

log "=== VPS INFRA DEPLOY START ==="

# 1. Docker + FlareSolverr
log "[1/4] Docker + FlareSolverr"
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh 2>&1 | tail -3
    sudo usermod -aG docker debian
    sudo systemctl enable --now docker
fi

if ! sudo docker ps | grep -q flaresolverr; then
    log "Starting FlareSolverr..."
    sudo docker rm -f flaresolverr 2>/dev/null
    sudo docker run -d \
        --name flaresolverr \
        --restart=always \
        -p 8191:8191 \
        -e LOG_LEVEL=info \
        -e CAPTCHA_SOLVER=none \
        -e TZ=Europe/Warsaw \
        ghcr.io/flaresolverr/flaresolverr:latest
    log "FlareSolverr starting (port 8191)..."
else
    log "FlareSolverr already running"
fi

# 2. SOCKS5 proxy
log "[2/4] SOCKS5 proxy"
chmod +x "$BASE/start_socks5.sh"
bash "$BASE/start_socks5.sh" 2>/dev/null || true

# 3. Scripts permissions
log "[3/4] Scripts permissions"
chmod +x "$BASE/check_proxy.sh" "$BASE/rotate_mobile_ip.sh" "$BASE/proxy_watchdog.sh" "$BASE/start_socks5.sh" 2>/dev/null

# 4. Cron jobs
log "[4/4] Cron jobs"
CRON_TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v "proxy_watchdog\|start_socks5\|docker.*flaresolverr" > "$CRON_TMP" || true
cat >> "$CRON_TMP" << 'CRON'
* * * * * /opt/pokemon-monitor-v2/proxy_watchdog.sh >/dev/null 2>&1
*/5 * * * * /opt/pokemon-monitor-v2/start_socks5.sh >/dev/null 2>&1
*/5 * * * * sudo docker start flaresolverr >/dev/null 2>&1
CRON
crontab "$CRON_TMP"
rm -f "$CRON_TMP"

log "=== DEPLOY DONE ==="
echo ""
echo "=== STATUS ==="
echo -n "  FlareSolverr: "
curl -s http://localhost:8191 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('msg','starting...'))" 2>/dev/null || echo "starting (wait 30s)..."
echo -n "  SOCKS5 :1080: "
ss -tlnp | grep -q ":1080" && echo "OK" || echo "DEAD (phone offline?)"
echo -n "  HTTP proxy:   "
curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 3 https://google.com 2>/dev/null || echo "DEAD"
echo ""
echo -n "  Mobile IP:    "
curl -x http://127.0.0.1:8888 -s --connect-timeout 5 ifconfig.me 2>/dev/null || echo "proxy offline"
echo ""
