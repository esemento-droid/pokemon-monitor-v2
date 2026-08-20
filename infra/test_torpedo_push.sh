#!/bin/bash
cd /opt/pokemon-monitor-v2
./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7437 > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "test output" && git push origin main
