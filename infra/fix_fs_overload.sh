#!/bin/bash
# Fix FlareSolverr CPU overload (166% CPU, 755/768MB)
# Root cause: challenge loops from failing shops eat all CPU
# bash infra/fix_fs_overload.sh | curl -sF 'file=@-' https://paste.rs

echo "=== FIX FS OVERLOAD ==="
echo "Data: $(date)"
echo ""

echo "--- BEFORE ---"
docker stats flaresolverr --no-stream --format "FS RAM: {{.MemUsage}} | CPU: {{.CPUPerc}}" 2>/dev/null
echo "Load: $(cat /proc/loadavg)"
echo ""

echo "--- 1. Restart FlareSolverr z 1GB RAM limit ---"
docker stop flaresolverr 2>/dev/null
sleep 3
docker rm flaresolverr 2>/dev/null
docker run -d --name flaresolverr --restart unless-stopped \
  --memory=1g \
  -e LOG_LEVEL=info \
  -e BROWSER_TIMEOUT=60000 \
  -e MAX_TIMEOUT=120000 \
  -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
echo "FS restarted with 1GB limit"
echo ""

sleep 5

echo "--- AFTER ---"
docker stats flaresolverr --no-stream --format "FS RAM: {{.MemUsage}} | CPU: {{.CPUPerc}}" 2>/dev/null
echo "Load: $(cat /proc/loadavg)"
echo ""

echo "--- 2. Czekam 30s na stabilizacje ---"
sleep 30
echo "Load po 30s: $(cat /proc/loadavg)"
docker stats flaresolverr --no-stream --format "FS RAM: {{.MemUsage}} | CPU: {{.CPUPerc}}" 2>/dev/null
echo ""

echo "=== DONE ==="
