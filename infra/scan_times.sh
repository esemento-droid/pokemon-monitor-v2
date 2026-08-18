#!/bin/bash
# Wyciaga czasy skanow + czestotliwosc z logow monitora (ostatnie 10 min)
# Uzycie: bash infra/scan_times.sh | curl -sF 'file=@-' https://paste.rs

echo "=== SCAN TIMES + CZESTOTLIWOSC (ostatnie 10 min) ==="
echo "Data: $(date)"
echo ""

LOGS=$(journalctl -u pokemon-monitor-v2 --since "10 min ago" --no-pager 2>/dev/null)

echo "--- TOP 30 NAJWOLNIEJSZYCH SKANOW ---"
echo "$LOGS" | grep -oP '\[\w+\] \d+ produktow w \d+\.?\d*s' | sort -t'w' -k2 -rn | head -30
echo ""

echo "--- SREDNI CZAS PER GRUPA ---"
echo "$LOGS" | grep -oP '\[\w+\] \d+ produktow w \d+\.?\d*s' | awk -F'[][ ]' '{
    shop=$2
    match($0, /w ([0-9.]+)s/, a)
    time=a[1]
    sum[shop]+=time
    count[shop]++
}
END {
    for(s in sum) {
        avg=sum[s]/count[s]
        printf "%6.1fs avg | %3d skanow | %s\n", avg, count[s], s
    }
}' | sort -rn | head -50
echo ""

echo "--- CZESTOTLIWOSC (skany per shop w 10 min) ---"
echo "$LOGS" | grep -oP '\[\w+\] \d+ produktow' | awk -F'[][ ]' '{count[$2]++} END {for(s in count) printf "%3d skanow/10min (%4.1f/min) | %s\n", count[s], count[s]/10.0, s}' | sort -rn | head -60
echo ""

echo "--- TIMEOUTY (ostatnie 10 min) ---"
echo "$LOGS" | grep -i "timeout" | grep -oP '\[\w+\]' | sort | uniq -c | sort -rn | head -20
echo ""

echo "--- BLEDY (ostatnie 10 min) ---"
echo "$LOGS" | grep -i "error\|exception\|fail" | grep -oP '\[\w+\]' | sort | uniq -c | sort -rn | head -20
echo ""

echo "--- PODSUMOWANIE ---"
TOTAL_SCANS=$(echo "$LOGS" | grep -c "produktow w")
TOTAL_TIMEOUTS=$(echo "$LOGS" | grep -ci "timeout")
TOTAL_ERRORS=$(echo "$LOGS" | grep -ci "error\|exception")
UNIQUE_SHOPS=$(echo "$LOGS" | grep -oP '\[\w+\] \d+ produktow' | awk -F'[][ ]' '{print $2}' | sort -u | wc -l)
echo "Skanow: $TOTAL_SCANS | Timeoutow: $TOTAL_TIMEOUTS | Bledow: $TOTAL_ERRORS | Unikalnych shopow: $UNIQUE_SHOPS"
echo "Scany/h (estymacja): $((TOTAL_SCANS * 6))"
