#!/bin/bash
# ================================================================
# NIGHT IP TEST — deploy to phone, runs fully automatic
#
# From VPS: bash infra/night_ip_test.sh deploy
#           bash infra/night_ip_test.sh check     (after 5:15)
#           bash infra/night_ip_test.sh cancel     (abort before 3:00)
#
# WHAT HAPPENS ON PHONE (fully automatic):
#   3:00  Cron triggers night_sleep.sh
#         → wake-lock → save IP → set flag → airplane ON → sleep loop
#   5:00  Sleep ends (or failsafe fires at 5:15)
#         → airplane OFF → wait network → fix DNS → get new IP
#         → restart tinyproxy + autossh → report to VPS → remove flag
#
# SAFETY LAYERS:
#   Layer 1: termux-wake-lock (prevents Doze from killing process)
#   Layer 2: Sleep as loop of 60s chunks (survives partial process freeze)
#   Layer 3: Failsafe cron at 5:15 forces airplane OFF unconditionally
#   Layer 4: Watchdog (every 1 min) skips during test (flag file)
#            but WILL restart services once flag removed
#   Layer 5: rotate_ip.sh skips during test (flag file)
#   Layer 6: Boot script restores everything if phone reboots
#   Layer 7: VPS proxy_watchdog.sh repairs from VPS side after 5:05
# ================================================================

PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"
VPS_IP_FILE="/opt/pokemon-monitor-v2/mobile_proxy_ip.txt"
LOG="/opt/pokemon-monitor-v2/data/night_ip_test.log"
WEBHOOK_FILE="/opt/pokemon-monitor-v2/discord_webhook_stats.txt"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"; }

send_discord() {
    local msg="$1"
    local webhook=$(cat "$WEBHOOK_FILE" 2>/dev/null)
    [ -z "$webhook" ] && return
    curl -s -X POST "$webhook" -H "Content-Type: application/json" \
        -d "{\"content\": \"$msg\"}" >/dev/null 2>&1
}

case "${1:-}" in
    deploy)
        log "=== DEPLOYING NIGHT IP TEST TO PHONE ==="
        
        OLD_IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null)
        [ -z "$OLD_IP" ] && OLD_IP=$(cat "$VPS_IP_FILE" 2>/dev/null || echo "unknown")
        echo "$OLD_IP" > /tmp/night_test_old_ip.txt
        log "Current IP: $OLD_IP"
        
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS bash << 'PHONEDEPLOY'
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"

mkdir -p ~/bin ~/logs

# =====================================================
# NIGHT SLEEP SCRIPT (runs at 3:00 via cron)
# =====================================================
cat > ~/bin/night_sleep.sh << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"
VPS_HOST="debian@146.59.45.228"
LOG="$HOME/logs/night_ip_test.log"
FLAG="$HOME/.night_test_active"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

# Prevent double-run
if [ -f "$FLAG" ]; then
    log "SKIP: night test already running (flag exists)"
    exit 0
fi

# === PHASE 1: PREPARE ===
termux-wake-lock 2>/dev/null
log "=== NIGHT IP TEST START ==="

# Save old IP
OLD_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
echo "$OLD_IP" > "$HOME/.night_test_old_ip"
log "OLD IP: $OLD_IP"

# Set flag — watchdog and rotate_ip.sh will skip while this exists
touch "$FLAG"

# === PHASE 2: SHUTDOWN + AIRPLANE ===
pkill autossh 2>/dev/null
pkill -f "ssh.*8888" 2>/dev/null
pkill tinyproxy 2>/dev/null
sleep 2

cmd connectivity airplane-mode enable 2>/dev/null
log "AIRPLANE ON"

# === PHASE 3: SLEEP 2 HOURS (loop of 60s for resilience) ===
# 7200s = 120 iterations of 60s
# Loop lets us survive partial process freezes better than one long sleep
SLEPT=0
TARGET=7200
while [ $SLEPT -lt $TARGET ]; do
    sleep 60
    SLEPT=$((SLEPT + 60))
done
log "SLEEP DONE ($SLEPT seconds)"

# === PHASE 4: WAKEUP ===
cmd connectivity airplane-mode disable 2>/dev/null
log "AIRPLANE OFF"

# Fix DNS (Android may lose resolver after airplane)
echo "nameserver 1.1.1.1" > $PREFIX/etc/resolv.conf
echo "nameserver 8.8.8.8" >> $PREFIX/etc/resolv.conf

# Wait for mobile data (max 2.5 min)
NETWORK_OK=0
for i in $(seq 1 75); do
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        log "Network UP after ${i}s"
        NETWORK_OK=1
        break
    fi
    sleep 2
done

if [ $NETWORK_OK -eq 0 ]; then
    log "ERROR: No network after 2.5 min! Failsafe at 5:15 will retry."
    rm -f "$FLAG"
    exit 1
fi

sleep 5

# === PHASE 5: CHECK NEW IP ===
NEW_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
log "NEW IP: $NEW_IP (was: $OLD_IP)"
echo "$NEW_IP" > "$HOME/.current_ip"

RESULT="UNCHANGED"
[ "$NEW_IP" != "$OLD_IP" ] && [ "$NEW_IP" != "unknown" ] && RESULT="CHANGED"
log "RESULT: $RESULT"

# === PHASE 6: RESTART SERVICES ===
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2

pkill -f "ssh.*8888" 2>/dev/null
sleep 1
autossh -M 0 -f -N \
    -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
    -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
    -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 $VPS_HOST
sleep 5

# Verify services running
pgrep -x tinyproxy >/dev/null || log "WARNING: tinyproxy not running after restart!"
pgrep -x autossh >/dev/null || log "WARNING: autossh not running after restart!"

# === PHASE 7: REPORT TO VPS ===
# Try 3 times (network might be flaky right after airplane)
REPORTED=0
for attempt in 1 2 3; do
    if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes $VPS_HOST \
        "echo '$NEW_IP' > /opt/pokemon-monitor-v2/mobile_proxy_ip.txt && echo '$(date '+%Y-%m-%d %H:%M:%S') NIGHT_TEST $RESULT: $OLD_IP -> $NEW_IP' >> /opt/pokemon-monitor-v2/data/night_ip_test.log" 2>/dev/null; then
        REPORTED=1
        log "Reported to VPS (attempt $attempt)"
        break
    fi
    sleep 10
done
[ $REPORTED -eq 0 ] && log "WARNING: Could not report to VPS (VPS will pick up new IP from proxy health check)"

# === CLEANUP ===
rm -f "$FLAG"
termux-wake-unlock 2>/dev/null
log "=== NIGHT IP TEST COMPLETE: $OLD_IP -> $NEW_IP ($RESULT) ==="
SCRIPT
chmod +x ~/bin/night_sleep.sh

# =====================================================
# FAILSAFE WAKEUP (cron at 5:15 — unconditional)
# =====================================================
cat > ~/bin/failsafe_wake.sh << 'FAILSAFE'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"
LOG="$HOME/logs/night_ip_test.log"
FLAG="$HOME/.night_test_active"

# Only act if flag still exists (means main script didn't finish)
if [ ! -f "$FLAG" ]; then
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') FAILSAFE TRIGGERED (main script didn't complete)" >> "$LOG"

# Force airplane OFF
cmd connectivity airplane-mode disable 2>/dev/null

# Fix DNS
echo "nameserver 1.1.1.1" > $PREFIX/etc/resolv.conf
echo "nameserver 8.8.8.8" >> $PREFIX/etc/resolv.conf

# Wait for network
for i in $(seq 1 30); do
    ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && break
    sleep 2
done
sleep 3

# Restart services
pkill -9 tinyproxy 2>/dev/null
pkill -9 autossh 2>/dev/null
pkill -9 -f "ssh.*8888" 2>/dev/null
sleep 2
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2
autossh -M 0 -f -N \
    -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
    -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
    -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228

# Remove flag
rm -f "$FLAG"
echo "$(date '+%Y-%m-%d %H:%M:%S') FAILSAFE COMPLETE — services restored" >> "$LOG"
FAILSAFE
chmod +x ~/bin/failsafe_wake.sh

# =====================================================
# PATCH WATCHDOG — skip during night test
# =====================================================
# Add flag check at the beginning of watchdog
if ! grep -q "night_test_active" ~/bin/watchdog.sh 2>/dev/null; then
    sed -i '3a\
# Skip during night IP test\
if [ -f "$HOME/.night_test_active" ]; then exit 0; fi' ~/bin/watchdog.sh 2>/dev/null
fi

# Patch rotate_ip.sh — skip during night test
if ! grep -q "night_test_active" ~/bin/rotate_ip.sh 2>/dev/null; then
    sed -i '/KNOWN_STATIC_IP/a\
# Skip during night IP test\
if [ -f "$HOME/.night_test_active" ]; then log "SKIP: night test active"; exit 0; fi' ~/bin/rotate_ip.sh 2>/dev/null
fi

# =====================================================
# SET CRON — add night test at 3:00 + failsafe at 5:15
# =====================================================
# Keep existing crons, add night test ones
EXISTING=$(crontab -l 2>/dev/null | grep -v "night_sleep" | grep -v "failsafe_wake" | grep -v "^$")
(echo "$EXISTING"; echo "0 3 * * * $HOME/bin/night_sleep.sh"; echo "15 5 * * * $HOME/bin/failsafe_wake.sh") | crontab -

echo "=== DEPLOY COMPLETE ==="
echo "Crontab:"
crontab -l
echo ""
echo "Night test will run automatically at 3:00 tonight."
echo "Failsafe at 5:15 guarantees recovery."
PHONEDEPLOY
        
        if [ $? -eq 0 ]; then
            log "Deploy successful!"
            log "Schedule: 3:00 airplane ON → 5:00 airplane OFF → check IP → restore"
            log "Failsafe: 5:15 forces recovery if anything goes wrong"
            send_discord "🌙 **NIGHT IP TEST deployed.** Schedule: 3:00→5:00 airplane mode. Failsafe at 5:15. Current IP: \`$OLD_IP\`"
            echo ""
            echo "DONE. Night test will run automatically tonight at 3:00."
            echo "Check results after 5:10: bash infra/night_ip_test.sh check"
        else
            log "ERROR: Deploy failed!"
            send_discord "❌ **NIGHT IP TEST deploy failed** — cannot SSH to phone"
            exit 1
        fi
        ;;
        
    check)
        OLD_IP=$(cat /tmp/night_test_old_ip.txt 2>/dev/null || echo "unknown")
        NEW_IP=$(cat "$VPS_IP_FILE" 2>/dev/null || echo "unknown")
        PROXY_OK=$(curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://google.com 2>/dev/null)
        LIVE_IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null || echo "TIMEOUT")
        
        echo "=== NIGHT IP TEST RESULTS ==="
        echo "  Old IP (before):   $OLD_IP"
        echo "  IP file (VPS):     $NEW_IP"
        echo "  Live proxy IP:     $LIVE_IP"
        echo "  Proxy HTTP status: $PROXY_OK"
        echo ""
        
        if [ "$LIVE_IP" != "TIMEOUT" ] && [ "$LIVE_IP" != "unknown" ] && [ "$LIVE_IP" != "$OLD_IP" ]; then
            echo "  🎉 IP CHANGED! $OLD_IP → $LIVE_IP"
            echo "  → 2h airplane mode WORKS for Orange PL rotation!"
            send_discord "🎉 **NIGHT TEST SUCCESS!** IP: \`$OLD_IP\` → \`$LIVE_IP\`. Nightly rotation is viable!"
        elif [ "$LIVE_IP" = "$OLD_IP" ]; then
            echo "  😐 IP UNCHANGED: $LIVE_IP"
            echo "  → Orange holds IP even after 2h. Need Play SIM."
            send_discord "😐 **NIGHT TEST:** IP unchanged (\`$LIVE_IP\`). Orange trzyma. Trzeba Play SIM."
        elif [ "$LIVE_IP" = "TIMEOUT" ]; then
            echo "  ⚠️ PROXY NOT RESPONDING"
            echo "  → Phone may still be recovering. Wait 5 min or check phone."
            # Try tailscale
            echo -n "  Tailscale ping: "
            tailscale ping --timeout=5s $PHONE_TS 2>&1 | head -1
        fi
        
        echo ""
        echo "=== Phone log ==="
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS \
            'cat ~/logs/night_ip_test.log 2>/dev/null' 2>/dev/null | tail -15 || echo "  (cannot reach phone)"
        ;;
        
    cancel)
        log "=== CANCELLING NIGHT TEST ==="
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS '
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
# Remove night test crons
crontab -l 2>/dev/null | grep -v "night_sleep" | grep -v "failsafe_wake" | crontab -
# Remove flag if exists
rm -f "$HOME/.night_test_active"
echo "Night test cancelled. Crontab:"
crontab -l
' 2>/dev/null
        log "Night test cancelled."
        echo "Night test cancelled."
        ;;
        
    *)
        echo "Usage: bash infra/night_ip_test.sh {deploy|check|cancel}"
        echo ""
        echo "  deploy — Install on phone (runs automatically at 3:00 tonight)"
        echo "  check  — See results (run after 5:10)"
        echo "  cancel — Remove night test from phone cron"
        ;;
esac
