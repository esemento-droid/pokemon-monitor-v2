#!/bin/bash
# Phone health check + repair — run from VPS
# Checks proxy paths, phone processes, repairs if needed
PHONE_TS="100.127.72.24"
PHONE_PORT="8022"
PHONE_PASS="123"

echo "=== PROXY PATHS (from VPS) ==="
echo -n "Tunnel (8888): "
curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code} (%{time_total}s)" --connect-timeout 5 --max-time 10 https://google.com
echo ""
echo -n "Tailscale direct: "
curl -x http://${PHONE_TS}:8888 -s -o /dev/null -w "%{http_code} (%{time_total}s)" --connect-timeout 5 --max-time 10 https://google.com
echo ""
echo -n "SOCKS5 (1080): "
curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code} (%{time_total}s)" --connect-timeout 5 --max-time 10 https://google.com
echo ""

echo ""
echo "=== MOBILE IP ==="
echo -n "via tunnel: "
curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null || echo "TIMEOUT"
echo ""
echo -n "via tailscale: "
curl -x http://${PHONE_TS}:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null || echo "TIMEOUT"
echo ""
echo -n "mobile_proxy_ip.txt: "
cat /opt/pokemon-monitor-v2/mobile_proxy_ip.txt 2>/dev/null || echo "MISSING"
echo ""

echo ""
echo "=== TAILSCALE PING ==="
tailscale ping --timeout=5s $PHONE_TS 2>&1 | head -1

echo ""
echo "=== PHONE STATUS (via SSH) ==="
sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS '
echo "--- processes ---"
pgrep -x tinyproxy >/dev/null && echo "tinyproxy: OK" || echo "tinyproxy: DEAD"
pgrep -x autossh >/dev/null && echo "autossh: OK" || echo "autossh: DEAD"
pgrep -x crond >/dev/null && echo "crond: OK" || echo "crond: DEAD"
echo "--- watchdog log (last 10) ---"
tail -10 ~/logs/watchdog.log 2>/dev/null
echo "--- rotation log (last 5) ---"
tail -5 ~/logs/ip_rotation.log 2>/dev/null
echo "--- rotate_ip.sh version check ---"
grep -q "KNOWN_STATIC_IP" ~/bin/rotate_ip.sh 2>/dev/null && echo "rotate_ip.sh: HAS static IP guard" || echo "rotate_ip.sh: OLD (no guard)"
echo "--- watchdog.sh version check ---"
grep -q "VPS UNREACHABLE" ~/bin/watchdog.sh 2>/dev/null && echo "watchdog.sh: HAS VPS check" || echo "watchdog.sh: BASIC (pgrep only)"
' 2>/dev/null

echo ""
echo "=== REPAIR NEEDED? ==="
TUNNEL_OK=$(curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null)
TS_OK=$(curl -x http://${PHONE_TS}:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://google.com 2>/dev/null)
if echo "$TUNNEL_OK" | grep -q "200\|301"; then
    echo "NO — tunnel works fine"
elif echo "$TS_OK" | grep -q "200\|301"; then
    echo "TUNNEL DEAD but Tailscale OK — restarting autossh on phone..."
    sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS \
        'pkill autossh; pkill -f "ssh.*8888"; sleep 2; autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228' 2>/dev/null
    sleep 5
    curl -x http://127.0.0.1:8888 -s -o /dev/null -w "After repair tunnel: %{http_code}" --connect-timeout 5 https://google.com
    echo ""
else
    echo "BOTH DEAD — full repair..."
    sshpass -p "$PHONE_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $PHONE_PORT $PHONE_TS '
pkill -9 tinyproxy; pkill -9 autossh; pkill -9 -f "ssh.*8888"; sleep 2
echo "nameserver 1.1.1.1" > $PREFIX/etc/resolv.conf
echo "nameserver 8.8.8.8" >> $PREFIX/etc/resolv.conf
tinyproxy -c $PREFIX/etc/tinyproxy/tinyproxy.conf 2>/dev/null || tinyproxy
sleep 2
autossh -M 0 -f -N -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=no" -R 8888:127.0.0.1:8888 -R 2222:127.0.0.1:8022 debian@146.59.45.228' 2>/dev/null
    sleep 5
    curl -x http://127.0.0.1:8888 -s -o /dev/null -w "After full repair tunnel: %{http_code}" --connect-timeout 5 https://google.com
    echo ""
fi
