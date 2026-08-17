#!/bin/bash
# ================================================================
# NIGHT IP TEST — 2h airplane mode, check if Orange PL changes IP
#
# Run from VPS: bash infra/night_ip_test.sh start
#
# SAFETY:
#   - Phone has a FAILSAFE cron that disables airplane at 5:15 NO MATTER WHAT
#   - termux-wake-lock prevents Doze from killing the process
#   - Even if sleep script dies, failsafe cron + watchdog recover everything
#   - If VPS can't reach phone after 5:30 → Discord alert
#
# FLOW:
#   1. VPS SSHs to phone → deploys failsafe cron + sleep script
#   2. Phone: kills services → airplane ON → sleep 2h → airplane OFF
#   3. Phone: waits for network → restarts services → reports IP to VPS
#   4. Failsafe: at 5:15 phone cron forces airplane OFF regardless
#   5. VPS: at 5:30 checks result (cron or manual)
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
    start)
        log "=== NIGHT IP TEST: DEPLOYING ==="
        
        # Save current IP
        OLD_IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null)
        [ -z "$OLD_IP" ] && OLD_IP=$(cat "$VPS_IP_FILE" 2>/dev/null || echo "unknown")
        echo "$OLD_IP" > /tmp/night_test_old_ip.txt
        log "Current IP: $OLD_IP"
        
        # Deploy to phone: failsafe cron + night test script
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS bash << 'DEPLOY'
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"

# === FAILSAFE CRON ===
# This runs at 5:15 and FORCES airplane OFF + service restart
# Even if sleep script dies, this guarantees recovery
cat > ~/bin/failsafe_wake.sh << 'FAILSAFE'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"
LOG="$HOME/logs/night_ip_test.log"

# Force airplane OFF
cmd connectivity airplane-mode disable 2>/dev/null

# Wait for network
for i in $(seq 1 30); do
    ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && break
    sleep 2
done
sleep 3

# Ensure services running (watchdog will also do this, but be safe)
if ! pgrep -x tinyproxy >/dev/null 2>&1; then
    tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
fi
if ! pgrep -x autossh >/dev/null 2>&1; then
    pkill -f "ssh.*8888" 2>/dev/null
    sleep 1
    autossh -M 0 -f -N \
        -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
        -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
        -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') FAILSAFE: airplane OFF, services checked" >> "$LOG"

# Remove failsafe from cron (one-time only)
crontab -l 2>/dev/null | grep -v "failsafe_wake" | grep -v "^$" | crontab -
FAILSAFE
chmod +x ~/bin/failsafe_wake.sh

# Add failsafe to cron (5:15) — alongside normal watchdog + rotation
(crontab -l 2>/dev/null | grep -v "failsafe_wake"; echo "15 5 * * * $HOME/bin/failsafe_wake.sh") | crontab -

# === NIGHT TEST SCRIPT ===
cat > ~/bin/night_sleep.sh << 'NIGHTSLEEP'
#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"
VPS_HOST="debian@146.59.45.228"
LOG="$HOME/logs/night_ip_test.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

# Wake lock — prevents Android Doze from killing us during sleep
termux-wake-lock 2>/dev/null

# Get current IP before shutdown
OLD_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
log "=== NIGHT TEST START === OLD IP: $OLD_IP"

# Kill services (clean shutdown)
pkill autossh 2>/dev/null
pkill -f "ssh.*8888" 2>/dev/null
pkill tinyproxy 2>/dev/null
sleep 2

# AIRPLANE ON
cmd connectivity airplane-mode enable 2>/dev/null
log "AIRPLANE ON — sleeping 7200s (2h)"

# Sleep 2 hours (wake-lock keeps process alive through Doze)
sleep 7200

# === WAKEUP ===
log "WAKING UP"

# AIRPLANE OFF
cmd connectivity airplane-mode disable 2>/dev/null
log "AIRPLANE OFF — waiting for network"

# Wait for mobile data (max 2 min)
NETWORK_OK=0
for i in $(seq 1 60); do
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        log "Network UP after ${i}s"
        NETWORK_OK=1
        break
    fi
    sleep 2
done

if [ $NETWORK_OK -eq 0 ]; then
    log "ERROR: Network not back after 2 min!"
    # Failsafe cron at 5:15 will handle recovery
    exit 1
fi

sleep 5

# Get new IP
NEW_IP=$(curl -s --connect-timeout 10 ifconfig.me 2>/dev/null || echo "unknown")
log "NEW IP: $NEW_IP (was: $OLD_IP)"

# Save IP locally
echo "$NEW_IP" > "$HOME/.current_ip"

# Restart services
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy 2>/dev/null
sleep 2
autossh -M 0 -f -N \
    -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
    -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" \
    -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 $VPS_HOST
sleep 5

# Report result to VPS
RESULT="UNCHANGED"
[ "$NEW_IP" != "$OLD_IP" ] && [ "$NEW_IP" != "unknown" ] && RESULT="CHANGED"
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes $VPS_HOST \
    "echo '$NEW_IP' > /opt/pokemon-monitor-v2/mobile_proxy_ip.txt; echo '$(date '+%Y-%m-%d %H:%M:%S') NIGHT TEST $RESULT: $OLD_IP -> $NEW_IP' >> /opt/pokemon-monitor-v2/data/night_ip_test.log" 2>/dev/null

log "=== NIGHT TEST COMPLETE: $RESULT ($OLD_IP -> $NEW_IP) ==="

# Release wake lock
termux-wake-unlock 2>/dev/null
NIGHTSLEEP
chmod +x ~/bin/night_sleep.sh

echo "DEPLOY OK — failsafe cron set, night_sleep.sh ready"
DEPLOY
        
        if [ $? -ne 0 ]; then
            log "ERROR: Cannot deploy to phone!"
            send_discord "❌ **NIGHT IP TEST FAILED** — cannot SSH to phone"
            exit 1
        fi
        
        log "Scripts deployed. Starting night sleep on phone (nohup)..."
        
        # Run night_sleep.sh on phone in background (nohup + disown)
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS \
            'nohup ~/bin/night_sleep.sh > ~/logs/night_sleep_output.log 2>&1 &' 2>> "$LOG"
        
        sleep 2
        log "Night test STARTED on phone."
        log "Phone will be offline from NOW until ~$(date -d '+2 hours' '+%H:%M' 2>/dev/null || echo '~2h from now')"
        log "Failsafe cron at 5:15 guarantees recovery."
        send_discord "🌙 **NIGHT IP TEST** running! Phone offline for 2h. IP before: \`$OLD_IP\`. Failsafe at 5:15. Result in \`mobile_proxy_ip.txt\` after ~5:05."
        ;;
        
    check)
        # === Run after 5:30 to see results ===
        log "=== NIGHT IP TEST: CHECKING RESULTS ==="
        
        OLD_IP=$(cat /tmp/night_test_old_ip.txt 2>/dev/null || echo "unknown")
        NEW_IP=$(cat "$VPS_IP_FILE" 2>/dev/null || echo "unknown")
        
        # Test if proxy works now
        PROXY_STATUS=$(curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://google.com 2>/dev/null)
        LIVE_IP=$(curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null || echo "TIMEOUT")
        
        echo "=== NIGHT IP TEST RESULTS ==="
        echo "  Old IP (before test): $OLD_IP"
        echo "  IP file now:          $NEW_IP"
        echo "  Live proxy IP:        $LIVE_IP"
        echo "  Proxy status:         $PROXY_STATUS"
        echo ""
        
        if [ "$LIVE_IP" != "$OLD_IP" ] && [ "$LIVE_IP" != "TIMEOUT" ] && [ "$LIVE_IP" != "unknown" ]; then
            echo "  🎉 RESULT: IP CHANGED! ($OLD_IP → $LIVE_IP)"
            echo "  → Orange PL rotates IP after 2h offline!"
            echo "  → Can schedule nightly rotation (free, no second SIM needed)"
            send_discord "🎉 **NIGHT IP TEST: SUCCESS!** IP zmienione: \`$OLD_IP\` → \`$LIVE_IP\`! Nightly rotation działa!"
        elif [ "$LIVE_IP" = "$OLD_IP" ]; then
            echo "  😐 RESULT: IP UNCHANGED ($LIVE_IP)"
            echo "  → Orange PL holds IP even after 2h offline"
            echo "  → Need Play SIM for rotation"
            send_discord "😐 **NIGHT IP TEST: IP unchanged** (\`$LIVE_IP\`). Orange trzyma IP mimo 2h offline. Potrzebna SIM Play."
        else
            echo "  ❌ RESULT: Proxy not responding! ($PROXY_STATUS)"
            echo "  → Phone may still be recovering. Try again in 5 min."
            send_discord "⚠️ **NIGHT IP TEST** — proxy nie odpowiada po teście. Sprawdź telefon."
        fi
        
        # Cleanup
        rm -f /tmp/night_test_old_ip.txt
        
        # Show phone log
        echo ""
        echo "=== Phone night test log ==="
        sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS \
            'cat ~/logs/night_ip_test.log 2>/dev/null | tail -10' 2>/dev/null || echo "  (cannot reach phone)"
        ;;
        
    *)
        echo "Usage: bash infra/night_ip_test.sh {start|check}"
        echo ""
        echo "  start — Deploy + run (phone goes offline for 2h)"
        echo "  check — Check results (run after phone wakes up, ~5:10+)"
        echo ""
        echo "Tonight:"
        echo "  1. Now:   bash infra/night_ip_test.sh start"
        echo "  2. 5:10+: bash infra/night_ip_test.sh check"
        ;;
esac
