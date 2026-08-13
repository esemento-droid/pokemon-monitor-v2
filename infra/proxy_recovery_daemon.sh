#!/usr/bin/env bash
# Persistent proxy supervisor. Runs on the VPS under systemd.
# Adds a second recovery layer without changing the existing monitor or cron jobs.
set -u

BASE="/opt/pokemon-monitor-v2"
LOG="$BASE/data/proxy_recovery.log"
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"
VPS_HOST="debian@146.59.45.228"
INTERVAL=30

mkdir -p "$BASE/data"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

proxy_ok() {
    local proxy="$1"
    local code
    code="$(curl --noproxy '' --proxy "$proxy" -sS -o /dev/null -w '%{http_code}' \
        --connect-timeout 5 --max-time 12 https://www.google.com 2>/dev/null || true)"
    case "$code" in
        200|301|302) return 0 ;;
        *) return 1 ;;
    esac
}

socks_ok() {
    local code
    code="$(curl --noproxy '' --socks5-hostname 127.0.0.1:1080 -sS -o /dev/null -w '%{http_code}' \
        --connect-timeout 5 --max-time 12 https://www.google.com 2>/dev/null || true)"
    case "$code" in
        200|301|302) return 0 ;;
        *) return 1 ;;
    esac
}

phone_reachable() {
    tailscale ping --timeout=5s "$PHONE_TS" >/dev/null 2>&1
}

remote_restart_tunnel() {
    sshpass -p "$PHONE_PASS" ssh -o BatchMode=no -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 -p "$PHONE_PORT" "$PHONE_TS" 'bash -s' <<'REMOTE'
set +e
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PATH="$PREFIX/bin:$PATH"
VPS_HOST="debian@146.59.45.228"
LOG="$HOME/logs/proxy_recovery.log"
mkdir -p "$HOME/logs"
for pid in $(pgrep -f '[a]utossh.*-R 8888' 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
for pid in $(pgrep -f '[s]sh.*-R 8888' 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
sleep 2
nohup autossh -M 0 -f -N \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no \
  -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 "$VPS_HOST" \
  >>"$LOG" 2>&1 </dev/null
REMOTE
}

remote_repair_phone() {
    sshpass -p "$PHONE_PASS" ssh -o BatchMode=no -o StrictHostKeyChecking=no \
        -o ConnectTimeout=10 -p "$PHONE_PORT" "$PHONE_TS" 'bash -s' <<'REMOTE'
set +e
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PATH="$PREFIX/bin:$PATH"
VPS_HOST="debian@146.59.45.228"
LOG="$HOME/logs/proxy_recovery.log"
CONF="$PREFIX/etc/tinyproxy/tinyproxy.conf"
mkdir -p "$HOME/logs" "$PREFIX/etc/tinyproxy"
for pid in $(pgrep -f '[a]utossh.*-R 8888' 2>/dev/null || true); do kill -9 "$pid" 2>/dev/null || true; done
for pid in $(pgrep -f '[s]sh.*-R 8888' 2>/dev/null || true); do kill -9 "$pid" 2>/dev/null || true; done
pkill -9 -x tinyproxy 2>/dev/null || true
sleep 2
if [ ! -f "$CONF" ]; then
  cat > "$CONF" <<CONFEOF
User root
Group root
Port 8888
Timeout 600
DefaultErrorFile "$PREFIX/share/tinyproxy/default.html"
StatFile "$PREFIX/share/tinyproxy/stats.html"
LogLevel Warning
LogFile "$HOME/logs/tinyproxy.log"
MaxClients 50
ViaProxyName "tinyproxy"
ConnectPort 443
ConnectPort 563
ConnectPort 80
CONFEOF
fi
nohup tinyproxy -c "$CONF" >>"$LOG" 2>&1 </dev/null
sleep 2
nohup autossh -M 0 -f -N \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no \
  -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 "$VPS_HOST" \
  >>"$LOG" 2>&1 </dev/null
REMOTE
}

restart_socks() {
    for pid in $(pgrep -f '[s]sh.*-D 1080' 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
    sleep 1
    sshpass -p "$PHONE_PASS" ssh -o BatchMode=no -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -o ConnectTimeout=10 -f -N -D 1080 -p "$PHONE_PORT" "$PHONE_TS" \
        >/dev/null 2>&1 || true
}

last_tunnel=unknown
last_ts=unknown
last_socks=unknown
log "SUPERVISOR STARTED"

while true; do
    tunnel=down
    ts=down
    socks=down
    proxy_ok "http://127.0.0.1:8888" && tunnel=up
    proxy_ok "http://$PHONE_TS:8888" && ts=up
    socks_ok && socks=up

    if [ "$tunnel" != "$last_tunnel" ] || [ "$ts" != "$last_ts" ] || [ "$socks" != "$last_socks" ]; then
        log "STATUS tunnel=$tunnel tailscale=$ts socks5=$socks"
        last_tunnel="$tunnel"
        last_ts="$ts"
        last_socks="$socks"
    fi

    if [ "$tunnel" = down ] && [ "$ts" = up ]; then
        log "REPAIR tunnel: Tailscale proxy is healthy"
        remote_restart_tunnel || log "REPAIR tunnel SSH failed"
        sleep 5
    elif [ "$tunnel" = down ] && [ "$ts" = down ] && phone_reachable; then
        log "REPAIR phone: both HTTP paths are down, Tailscale device reachable"
        remote_repair_phone || log "REPAIR phone SSH failed"
        sleep 5
    fi

    if [ "$socks" = down ] && phone_reachable; then
        log "REPAIR socks5: restarting dynamic SSH forward"
        restart_socks
    fi

    sleep "$INTERVAL"
done
