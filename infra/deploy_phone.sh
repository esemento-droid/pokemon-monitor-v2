#!/bin/bash
# ================================================================
# DEPLOY PHONE (MI-9T) INFRASTRUCTURE
# Run from VPS: cd /opt/pokemon-monitor-v2 && bash infra/deploy_phone.sh
# Connects to mi-9t via Tailscale SSH and deploys everything
# ================================================================
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"
BASE="/opt/pokemon-monitor-v2"

echo "=== DEPLOYING TO MI-9T (${PHONE_TS}) ==="

# Check connectivity
if ! tailscale ping --timeout=5s $PHONE_TS >/dev/null 2>&1; then
    echo "ERROR: Cannot reach mi-9t via Tailscale!"
    echo "Check if Tailscale is running on phone."
    exit 1
fi

# Deploy scripts
sshpass -p "$PHONE_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p $PHONE_PORT $PHONE_TS bash << 'REMOTE'
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"

echo "=== Installing packages ==="
pkg install -y cronie tinyproxy autossh openssh curl 2>&1 | tail -2

mkdir -p ~/bin ~/logs

# === TINYPROXY CONFIG ===
cat > $PREFIX/etc/tinyproxy/tinyproxy.conf << 'CONF'
User root
Group root
Port 8888
Timeout 600
DefaultErrorFile "/data/data/com.termux/files/usr/share/tinyproxy/default.html"
StatFile "/data/data/com.termux/files/usr/share/tinyproxy/stats.html"
LogLevel Warning
LogFile "/data/data/com.termux/files/home/logs/tinyproxy.log"
MaxClients 200
ViaProxyName "tinyproxy"
ConnectPort 443
ConnectPort 563
ConnectPort 80
CONF

# === WATCHDOG ===
cat > ~/bin/watchdog.sh << 'WD'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
LOG="$HOME/logs/watchdog.log"
VPS_HOST="debian@146.59.45.228"

termux-wake-lock 2>/dev/null

# Tinyproxy — restart if dead
if ! pgrep -x tinyproxy >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') TINYPROXY DEAD - restarting" >> "$LOG"
    tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
    sleep 1
    pgrep -x tinyproxy >/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') TINYPROXY RESTORED" >> "$LOG"
fi

# Autossh — restart ONLY if process dead (NOT if tunnel flaps)
# VPS-side proxy_watchdog.sh handles tunnel repair from the other end
if ! pgrep -x autossh >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') AUTOSSH DEAD - restarting" >> "$LOG"
    pkill -f "ssh.*8888" 2>/dev/null
    sleep 2
    autossh -M 0 -f -N \
        -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
        -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
        -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 $VPS_HOST 2>> "$LOG"
    sleep 2
    pgrep -x autossh >/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') AUTOSSH RESTORED" >> "$LOG" \
        || echo "$(date '+%Y-%m-%d %H:%M:%S') AUTOSSH FAILED TO START" >> "$LOG"
fi

# On-demand rotation trigger
if [ -f "$HOME/.rotate_ip_now" ]; then
    rm -f "$HOME/.rotate_ip_now"
    $HOME/bin/rotate_ip.sh &
fi

# Log rotation (keep last 500 lines)
if [ -f "$LOG" ] && [ $(wc -l < "$LOG" 2>/dev/null || echo 0) -gt 2000 ]; then
    tail -500 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
WD
chmod +x ~/bin/watchdog.sh

# === IP ROTATION ===
cat > ~/bin/rotate_ip.sh << 'ROT'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
LOG="$HOME/logs/ip_rotation.log"
VPS_HOST="debian@146.59.45.228"
KNOWN_STATIC_IP="37.47.128.183"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

OLD_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")

# Skip if Orange PL static IP (airplane mode won't change it)
# Remove this check after swapping to dynamic SIM (Play/T-Mobile)
if [ "$OLD_IP" = "$KNOWN_STATIC_IP" ] && [ "$1" != "--force" ]; then
    log "ROTATION SKIPPED — Orange PL static IP ($OLD_IP). Swap SIM or use --force."
    exit 0
fi

log "ROTATE START - old IP: $OLD_IP"

pkill autossh 2>/dev/null
pkill -f "ssh.*8888" 2>/dev/null
pkill tinyproxy 2>/dev/null

cmd wifi set-wifi-enabled disabled 2>/dev/null

log "Airplane ON (15s)..."
cmd connectivity airplane-mode enable 2>> "$LOG"
sleep 15

log "Airplane OFF..."
cmd connectivity airplane-mode disable 2>> "$LOG"

log "Waiting for mobile data..."
for i in $(seq 1 30); do
    ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && { log "Network UP after ${i}s"; break; }
    sleep 1
done

sleep 3
NEW_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
log "NEW IP: $NEW_IP (was: $OLD_IP)"

if [ "$NEW_IP" = "$OLD_IP" ] && [ "$NEW_IP" != "unknown" ]; then
    log "SAME IP — retry 30s airplane..."
    cmd connectivity airplane-mode enable 2>> "$LOG"
    sleep 30
    cmd connectivity airplane-mode disable 2>> "$LOG"
    for i in $(seq 1 20); do
        ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && break; sleep 1
    done
    sleep 3
    NEW_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
    log "RETRY IP: $NEW_IP"
fi

echo "$NEW_IP" > "$HOME/.current_ip"

tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 1
autossh -M 0 -f -N \
    -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
    -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
    -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 $VPS_HOST 2>> "$LOG"
sleep 3

ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes $VPS_HOST \
    "echo '$NEW_IP' > /opt/pokemon-monitor-v2/mobile_proxy_ip.txt" 2>/dev/null

log "ROTATE COMPLETE: $OLD_IP -> $NEW_IP"
ROT
chmod +x ~/bin/rotate_ip.sh

# === CRON ===
(echo "* * * * * $HOME/bin/watchdog.sh"; echo "0 */4 * * * $HOME/bin/rotate_ip.sh") | crontab -
pkill crond 2>/dev/null; crond 2>/dev/null

# === BOOT SCRIPT ===
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start.sh << 'BOOT'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
termux-wake-lock
sleep 10
for i in $(seq 1 30); do ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && break; sleep 3; done
sshd
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2
autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228
sleep 2
crond
BOOT
chmod +x ~/.termux/boot/start.sh

# === START ===
pkill tinyproxy 2>/dev/null; pkill autossh 2>/dev/null; pkill -f "ssh.*8888" 2>/dev/null
sleep 2
termux-wake-lock 2>/dev/null
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2
autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228
sleep 2

echo ""
echo "=== PHONE DEPLOY DONE ==="
echo "Tinyproxy: $(pgrep -x tinyproxy >/dev/null && echo OK || echo DEAD)"
echo "Autossh:   $(pgrep -x autossh >/dev/null && echo OK || echo DEAD)"
echo "Crond:     $(pgrep -x crond >/dev/null && echo OK || echo DEAD)"
REMOTE

echo ""
echo "=== PHONE DEPLOYMENT COMPLETE ==="
echo "Verifying from VPS..."
sleep 5
echo -n "  Proxy tunnel: "
curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com
echo ""
echo -n "  Mobile IP:    "
curl -x http://127.0.0.1:8888 -s --connect-timeout 5 ifconfig.me
echo ""
