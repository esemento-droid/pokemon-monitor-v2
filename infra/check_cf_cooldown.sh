#!/bin/bash
# Check CF cooldown loop - what's happening with gralnia/xjoy/battlestash/tcgzielona
echo "=== CF SHOPS COOLDOWN ANALYSIS ===" > /tmp/cf_report.txt
echo "Generated: $(date)" >> /tmp/cf_report.txt
echo "" >> /tmp/cf_report.txt

echo "=== 1. CF SOLVER ERRORS (last 30min) ===" >> /tmp/cf_report.txt
journalctl -u pokemon-monitor-v2 --since "30 min ago" --no-pager 2>/dev/null | grep -i "CF_SOLVER" | tail -30 >> /tmp/cf_report.txt
echo "" >> /tmp/cf_report.txt

echo "=== 2. COOLDOWN ENTRIES (last 1h) ===" >> /tmp/cf_report.txt
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager 2>/dev/null | grep -iE "(cooldown|consecutive)" | tail -40 >> /tmp/cf_report.txt
echo "" >> /tmp/cf_report.txt

echo "=== 3. CF SHOPS ERRORS (gralnia/xjoy/battlestash/tcgzielona/strefamtg/maginarium/monsteriada) ===" >> /tmp/cf_report.txt
journalctl -u pokemon-monitor-v2 --since "30 min ago" --no-pager 2>/dev/null | grep -iE "\[(gralnia|xjoy|battlestash|tcgzielona|tcg-zielona|strefamtg|maginarium|monsteriada)\]" | tail -50 >> /tmp/cf_report.txt
echo "" >> /tmp/cf_report.txt

echo "=== 4. CF BRIDGE STATUS ===" >> /tmp/cf_report.txt
curl -s http://127.0.0.1:8191/ >> /tmp/cf_report.txt 2>&1
echo "" >> /tmp/cf_report.txt

echo "=== 5. PROXY STATUS RIGHT NOW ===" >> /tmp/cf_report.txt
curl -s --proxy http://127.0.0.1:8888 --max-time 5 http://httpbin.org/ip >> /tmp/cf_report.txt 2>&1
echo "" >> /tmp/cf_report.txt

echo "=== 6. CF SHOPS SCAN COUNTS + TIMES (from live_report data) ===" >> /tmp/cf_report.txt
echo "Shop             Scans   Avg    Errors  Timeouts" >> /tmp/cf_report.txt
journalctl -u pokemon-monitor-v2 --since "4 hours ago" --no-pager 2>/dev/null | grep -E "\[(gralnia|xjoy|battlestash|tcg-zielona|tcgzielona|sklepkleks|dystryktzero)\].*produkt" | awk -F'[][]' '{print $4}' | sort | uniq -c | sort -rn >> /tmp/cf_report.txt
echo "" >> /tmp/cf_report.txt

echo "=== 7. SUCCESSFUL SCANS PER CF SHOP (last 4h) ===" >> /tmp/cf_report.txt
for shop in gralnia xjoy battlestash tcg-zielona tcgzielona sklepkleks dystryktzero; do
  count=$(journalctl -u pokemon-monitor-v2 --since "4 hours ago" --no-pager 2>/dev/null | grep "\[$shop\]" | grep "produktow" | wc -l)
  last=$(journalctl -u pokemon-monitor-v2 --since "4 hours ago" --no-pager 2>/dev/null | grep "\[$shop\]" | grep "produktow" | tail -1)
  echo "  $shop: $count OK scans | Last: $last" >> /tmp/cf_report.txt
done
echo "" >> /tmp/cf_report.txt

echo "=== 8. CF SOLVER SEMAPHORE TEST ===" >> /tmp/cf_report.txt
curl -s -X POST http://127.0.0.1:8191/v1 -H "Content-Type: application/json" -d '{"cmd":"request.get","url":"https://gralnia.org/kategoria-produktu/pokemon-tcg/","maxTimeout":30000}' --max-time 45 | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\")}, HTML len: {len(d.get(\"solution\",{}).get(\"response\",\"\"))}')" >> /tmp/cf_report.txt 2>&1
echo "" >> /tmp/cf_report.txt

echo "=== END ===" >> /tmp/cf_report.txt
cat /tmp/cf_report.txt
