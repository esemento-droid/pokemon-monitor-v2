#!/bin/bash
# Diagnostyka: dlaczego FAST shopy sa wolne + status problematycznych
# bash infra/diag_slow.sh | curl -sF 'file=@-' https://paste.rs

echo "=== DIAGNOSTYKA WOLNYCH SHOPOW ==="
echo "Data: $(date)"
echo ""

echo "--- 1. FAST PROCESS: czy cos blokuje? (ostatnie 30 linii) ---"
journalctl -u pokemon-monitor-v2 --since "2 min ago" --no-pager | grep -i "\[FAST\]" | tail -30
echo ""

echo "--- 2. STREFAKART (powinno 3-5s, jest 100s) ---"
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep -i "strefakart" | tail -20
echo ""

echo "--- 3. EDUKSIAZKA / MEPEL / XJOY / GRALNIA (errors) ---"
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep -iE "eduksiazka|mepel|xjoy|gralnia" | tail -30
echo ""

echo "--- 4. PKMNSHOP / MYCARDS / TANTIS_OLD (SSL/timeout) ---"
journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager | grep -iE "pkmnshop|mycards|tantis_old" | tail -20
echo ""

echo "--- 5. CURL TEST: domeny zyja? ---"
for domain in pkmnshop.pl mycards.pl tantis.pl strefakart.pl; do
  code=$(curl -s -o /dev/null -w "%{http_code} %{time_total}s" --max-time 10 "https://$domain" 2>&1)
  echo "  $domain: $code"
done
echo ""

echo "--- 6. RAM + CPU teraz ---"
free -h | head -2
echo ""
echo "Load: $(uptime)"
echo "Chrome: $(pgrep -c chrome 2>/dev/null || echo 0) procesow"
echo "Python: $(pgrep -c python 2>/dev/null || echo 0) procesow"
echo ""

echo "--- 7. PROXY STATUS ---"
curl -s -o /dev/null -w "Tunnel HTTP: %{http_code} %{time_total}s\n" --proxy http://127.0.0.1:8888 --max-time 10 "https://httpbin.org/ip" 2>&1
curl -s -o /dev/null -w "SOCKS5: %{http_code} %{time_total}s\n" --proxy socks5h://127.0.0.1:1080 --max-time 10 "https://httpbin.org/ip" 2>&1
echo ""

echo "--- 8. FLARESOLVERR STATUS ---"
curl -s -o /dev/null -w "FS: %{http_code} %{time_total}s\n" --max-time 5 "http://localhost:8191" 2>&1
docker stats flaresolverr --no-stream --format "FS RAM: {{.MemUsage}} | CPU: {{.CPUPerc}}" 2>/dev/null
echo ""

echo "--- 9. TOP 10 NAJCZESCIEJ TIMEOUT (ostatnia godzina) ---"
journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager | grep -i "timeout" | grep -oP '\[\w+\]' | sort | uniq -c | sort -rn | head -10
echo ""

echo "--- 10. OGOLNE METRYKI (ostatnia godzina) ---"
LOGS1H=$(journalctl -u pokemon-monitor-v2 --since "1 hour ago" --no-pager)
echo "Scany: $(echo "$LOGS1H" | grep -c 'produktow w')"
echo "Timeouty: $(echo "$LOGS1H" | grep -ci 'timeout')"
echo "Errors: $(echo "$LOGS1H" | grep -ci 'error')"
echo ""
echo "=== KONIEC ==="
