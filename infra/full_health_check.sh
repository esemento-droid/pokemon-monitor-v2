#!/bin/bash
# Full system health check — proxy, phone, scrapers, auto-recovery, logs
# Run from VPS: bash infra/full_health_check.sh

echo "=========================================="
echo "  FULL SYSTEM HEALTH CHECK"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

echo ""
echo "=== 1. PROXY PATHS ==="
echo -n "  Tunnel (8888):    "
T1=$(curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 --max-time 10 https://google.com 2>/dev/null)
echo "$T1"
echo -n "  Tailscale direct: "
T2=$(curl -x http://100.127.72.24:8888 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 --max-time 10 https://google.com 2>/dev/null)
echo "$T2"
echo -n "  SOCKS5 (1080):    "
T3=$(curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 --max-time 10 https://google.com 2>/dev/null)
echo "$T3"
echo -n "  Mobile IP:        "
curl -x http://127.0.0.1:8888 -s --connect-timeout 5 --max-time 8 ifconfig.me 2>/dev/null || echo "TIMEOUT"
echo ""
echo -n "  VPS IP:           "
curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || echo "TIMEOUT"
echo ""
echo -n "  FlareSolverr:     "
curl -s --connect-timeout 5 http://localhost:8191 2>/dev/null | grep -q "FlareSolverr" && echo "OK" || echo "DEAD"

echo ""
echo "=== 2. PHONE STATUS (via Tailscale SSH) ==="
sshpass -p '123' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p 8022 100.127.72.24 '
echo "  Uptime: $(uptime -p 2>/dev/null || uptime)"
echo -n "  tinyproxy: "; pgrep -x tinyproxy >/dev/null && echo "OK (PID $(pgrep -x tinyproxy))" || echo "DEAD"
echo -n "  autossh:   "; pgrep -x autossh >/dev/null && echo "OK (PID $(pgrep -x autossh))" || echo "DEAD"
echo -n "  crond:     "; pgrep -x crond >/dev/null && echo "OK" || echo "DEAD"
echo -n "  rotate_ip: "; grep -q "KNOWN_STATIC_IP" ~/bin/rotate_ip.sh 2>/dev/null && echo "v2 (has guard)" || echo "v1 (old, no guard)"
echo -n "  watchdog:  "; grep -q "VPS UNREACHABLE" ~/bin/watchdog.sh 2>/dev/null && echo "v2 (VPS check)" || echo "v1 (pgrep only)"
echo "  --- last 5 watchdog ---"
tail -5 ~/logs/watchdog.log 2>/dev/null | sed "s/^/  /"
echo "  --- last 3 rotation ---"
tail -3 ~/logs/ip_rotation.log 2>/dev/null | sed "s/^/  /"
' 2>/dev/null || echo "  ERROR: Cannot SSH to phone!"

echo ""
echo "=== 3. MONITOR SERVICE ==="
echo -n "  systemd status: "
systemctl is-active pokemon-monitor-v2 2>/dev/null || echo "unknown"
echo -n "  uptime:         "
systemctl show pokemon-monitor-v2 --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2
echo -n "  PID:            "
systemctl show pokemon-monitor-v2 --property=MainPID 2>/dev/null | cut -d= -f2

echo ""
echo "=== 4. SCRAPER LOGS (last 5 min) ==="
LOGFILE="/opt/pokemon-monitor-v2/monitor.log"
if [ ! -f "$LOGFILE" ]; then
    LOGFILE=$(find /opt/pokemon-monitor-v2 -name "*.log" -newer /tmp -maxdepth 1 2>/dev/null | head -1)
fi
if [ -f "$LOGFILE" ]; then
    FIVE_AGO=$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M' 2>/dev/null || date -v-5M '+%Y-%m-%d %H:%M' 2>/dev/null)
    echo "  Log file: $LOGFILE"
    echo "  Lines last 5 min: $(grep -c "${FIVE_AGO:-$(date '+%Y-%m-%d %H')}" "$LOGFILE" 2>/dev/null || echo 'N/A')"
    echo "  --- last 20 lines ---"
    tail -20 "$LOGFILE" 2>/dev/null | sed 's/^/  /'
else
    echo "  No log file found, checking journalctl..."
    journalctl -u pokemon-monitor-v2 --since "5 min ago" --no-pager 2>/dev/null | tail -30 | sed 's/^/  /'
fi

echo ""
echo "=== 5. SCRAPER STATS (database) ==="
cd /opt/pokemon-monitor-v2
./venv/bin/python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
try:
    import asyncpg
    async def check():
        conn = await asyncpg.connect('postgresql://pokemonitor:mon2026pg@localhost/pokemonitor')
        # Total products
        total = await conn.fetchval('SELECT count(*) FROM products')
        # Active shops
        shops = await conn.fetch('SELECT shop, last_seen, error_count, scan_count FROM shop_state ORDER BY last_seen DESC LIMIT 15')
        # Recent events
        events = await conn.fetch(\"SELECT event_type, count(*) as cnt FROM event_log WHERE ts > now() - interval '1 hour' GROUP BY event_type ORDER BY cnt DESC\")
        # Errors last hour
        errors = await conn.fetchval(\"SELECT count(*) FROM event_log WHERE event_type='ERROR' AND ts > now() - interval '1 hour'\")
        await conn.close()
        print(f'  Total products in DB: {total}')
        print(f'  Errors last hour: {errors}')
        print(f'  Events last hour:')
        for e in events:
            print(f'    {e[\"event_type\"]:20s} {e[\"cnt\"]}')
        print(f'  Top 15 shops (by last_seen):')
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for s in shops:
            ago = (now - s['last_seen'].replace(tzinfo=timezone.utc)).total_seconds() if s['last_seen'] else 99999
            status = '✅' if ago < 300 else ('⚠️' if ago < 900 else '❌')
            ago_str = f'{int(ago)}s ago' if ago < 120 else f'{int(ago/60)}m ago'
            print(f'    {status} {s[\"shop\"]:25s} last_seen: {ago_str:10s} scans: {s[\"scan_count\"]:4} errs: {s[\"error_count\"]}')
    asyncio.run(check())
except Exception as e:
    print(f'  DB ERROR: {e}')
" 2>&1

echo ""
echo "=== 6. CRON JOBS (VPS) ==="
echo "  Active proxy-related crons:"
crontab -l 2>/dev/null | grep -E "proxy|socks|watchdog|health" | sed 's/^/  /'
if [ -z "$(crontab -l 2>/dev/null | grep -E 'proxy|socks|watchdog|health')" ]; then
    echo "  (none found — checking all crons)"
    crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | sed 's/^/  /'
fi

echo ""
echo "=== 7. DISK & MEMORY ==="
echo -n "  Disk: "; df -h /opt/pokemon-monitor-v2 2>/dev/null | tail -1 | awk '{print $4 " free (" $5 " used)"}'
echo -n "  RAM:  "; free -h 2>/dev/null | grep Mem | awk '{print $4 " free / " $2 " total"}'

echo ""
echo "=========================================="
echo "  HEALTH CHECK COMPLETE"
echo "=========================================="
