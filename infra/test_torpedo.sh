#!/bin/bash
# Test JC Torpedo DAEMON on test account (Marian Wasilewski)
# Product: Mega Heroes Mini Tin (ID=7437, 70 PLN, qty=17)
# This places a REAL order on the test account!

cd /opt/pokemon-monitor-v2

echo "=== Testing Torpedo Daemon (--fire mode, test account) ==="
DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7437 2>&1
echo ""
echo "=== Done ==="
