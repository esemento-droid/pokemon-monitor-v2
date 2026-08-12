#!/bin/bash
# Quick proxy health check — returns best available proxy URL
# Usage: PROXY=$(./check_proxy.sh) → use $PROXY
# Exit 0 = proxy URL on stdout, Exit 1 = all dead

# Priority: tunnel > tailscale > socks5
if curl -x http://127.0.0.1:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 3 https://google.com 2>/dev/null | grep -q "200\|301"; then
    echo "http://127.0.0.1:8888"
    exit 0
fi

if curl -x http://100.127.72.24:8888 -s -o /dev/null -w "%{http_code}" --connect-timeout 3 https://google.com 2>/dev/null | grep -q "200\|301"; then
    echo "http://100.127.72.24:8888"
    exit 0
fi

if curl --socks5-hostname 127.0.0.1:1080 -s -o /dev/null -w "%{http_code}" --connect-timeout 4 https://google.com 2>/dev/null | grep -q "200\|301"; then
    echo "socks5://127.0.0.1:1080"
    exit 0
fi

echo "DEAD" >&2
exit 1
