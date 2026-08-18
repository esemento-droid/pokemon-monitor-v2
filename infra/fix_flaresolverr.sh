#!/bin/bash
# Restart FlareSolverr with higher memory (768MB) — 512MB too tight, causes tab crashes
echo "=== FlareSolverr Fix $(date) ==="
docker stop flaresolverr 2>/dev/null || true
docker rm flaresolverr 2>/dev/null || true
sleep 2

docker run -d \
    --name flaresolverr \
    --restart unless-stopped \
    --memory=768m \
    --memory-swap=1g \
    -e LOG_LEVEL=info \
    -e TZ=Europe/Warsaw \
    -e HEADLESS=true \
    -e BROWSER_TIMEOUT=60000 \
    -e MAX_TIMEOUT=120000 \
    -p 8191:8191 \
    ghcr.io/flaresolverr/flaresolverr:latest

sleep 5
echo "Status:"
docker ps --filter name=flaresolverr --format "{{.Names}}: {{.Status}}"
docker inspect flaresolverr --format 'Memory limit: {{.HostConfig.Memory}}' 2>/dev/null
echo ""
echo "Health:"
curl -s --connect-timeout 5 http://localhost:8191/health 2>/dev/null || echo "  (starting up...)"
echo ""
echo "=== DONE ==="
