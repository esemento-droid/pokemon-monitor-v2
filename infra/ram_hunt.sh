#!/bin/bash
echo "=== RAM HUNT $(date) ==="
echo ""
echo "--- TOP 25 processes by RSS (MB) ---"
ps aux --sort=-rss | head -26 | awk '{printf "%-8s %6s %6s %s\n", $1, $6/1024"MB", $2, $11" "$12" "$13}' 
echo ""
echo "--- Chrome/Chromium processes ---"
ps aux | grep -i "chrom" | grep -v grep | wc -l
echo "Chrome process count: $(ps aux | grep -i chrom | grep -v grep | wc -l)"
echo ""
ps aux | grep -i "chrom" | grep -v grep | awk '{printf "PID=%s RSS=%sMB CMD=%s %s\n", $2, $6/1024, $11, $12}'
echo ""
echo "--- Python processes ---"
ps aux | grep python | grep -v grep | awk '{printf "PID=%s RSS=%sMB CMD=%s %s %s\n", $2, $6/1024, $11, $12, $13}'
echo ""
echo "--- Docker containers ---"
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}" 2>/dev/null
echo ""
echo "--- Memory summary by process name ---"
ps aux | awk 'NR>1 {a[$11]+=$6} END {for(i in a) if(a[i]>50000) printf "%6dMB  %s\n", a[i]/1024, i}' | sort -rn
echo ""
echo "--- Swap ---"
free -h
echo ""
swapon --show 2>/dev/null || echo "no swap"
echo ""
echo "--- Nodriver/patchright zombie check ---"
ps aux | grep -E "(nodriver|patchright|Xvfb)" | grep -v grep
echo ""
echo "--- Open file descriptors (top 5 PIDs) ---"
for pid in $(ps aux --sort=-rss | awk 'NR>1 && NR<7 {print $2}'); do echo "PID $pid: $(ls /proc/$pid/fd 2>/dev/null | wc -l) fds"; done
echo ""
echo "=== END ==="
