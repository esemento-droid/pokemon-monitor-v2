#!/bin/bash
cd /opt/pokemon-monitor-v2
DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7437 > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
# Also grab HTML dump if exists
if [ -f /tmp/jc_torpedo_cart_dump.html ]; then
  head -c 50000 /tmp/jc_torpedo_cart_dump.html > torpedo_cart_dump.html
fi
git add torpedo_test_output.txt torpedo_cart_dump.html 2>/dev/null; git commit -m "test output" && git push origin main
