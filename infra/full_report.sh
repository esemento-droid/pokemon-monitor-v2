#!/bin/bash
echo "=== FULL REPORT $(date) ==="
echo ""

echo "--- 1. Monitor status ---"
systemctl status pokemon-monitor-v2 --no-pager 2>&1 | grep -E "Active:|Main PID|ago"
echo ""

echo "--- 2. RAM ---"
free -h | head -2
echo ""

echo "--- 3. Chrome/FS ---"
echo "Chrome: $(pgrep -fc 'chromium|chrome-headless' 2>/dev/null || echo 0)"
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}" flaresolverr 2>/dev/null
echo ""

echo "--- 4. Proxy ---"
echo -n "Tunnel: "; curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 https://api.ipify.org; echo ""
echo -n "SOCKS5: "; curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 https://api.ipify.org; echo ""
echo ""

echo "--- 5. Limango last scan ---"
journalctl -u pokemon-monitor-v2 --since "30 min ago" --no-pager -o cat 2>/dev/null | grep -i "limango" | tail -10
echo ""

echo "--- 6. Discord webhook test ---"
WH=$(cat /opt/pokemon-monitor-v2/discord_webhook_limango.txt 2>/dev/null || cat /opt/pokemon-monitor-v2/discord_webhook_jc.txt 2>/dev/null)
if [ -n "$WH" ]; then
    echo "Webhook file found"
    echo "URL (first 50): ${WH:0:50}..."
else
    echo "NO WEBHOOK FILE FOUND!"
fi
echo ""

echo "--- 7. Last 20 monitor logs ---"
journalctl -u pokemon-monitor-v2 -n 20 --no-pager -o cat 2>/dev/null
echo ""

echo "--- 8. Limango in DB ---"
./venv/bin/python3 -c "
import asyncio, sys
sys.path.insert(0, '/opt/pokemon-monitor-v2')
async def check():
    from database import init_db, get_shop_products, is_snapshot_done
    await init_db()
    p = await get_shop_products('limango')
    snap = await is_snapshot_done('limango')
    print(f'  DB products: {len(p)}')
    print(f'  Snapshot done: {snap}')
    if p:
        sample = list(p.values())[:3]
        for s in sample:
            print(f'    {s.get(\"name\",\"?\")[:50]} | avail={s.get(\"available\")}')
asyncio.run(check())
" 2>/dev/null
echo ""

echo "--- 9. memory_guard log (last 5) ---"
tail -5 /opt/pokemon-monitor-v2/data/memory_guard.log 2>/dev/null || echo "(empty)"
echo ""

echo "--- 10. Errors last 30min ---"
journalctl -u pokemon-monitor-v2 --since "30 min ago" --no-pager -o cat 2>/dev/null | grep -iE "error|crash|fail" | grep -v "FlareSolverr" | tail -10
echo ""

echo "=== END REPORT ==="
