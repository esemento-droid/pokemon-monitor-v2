#!/bin/bash
cd /opt/pokemon-monitor-v2

# Final torpedo test: stage with Mini Tin (7437), fire on Kanto Tin (7589)
# Proves: pre-staged checkout + cart swap + submit = ~2s
DISPLAY=:99 ./venv/bin/python3 jc_torpedo_daemon.py --test --fire 7589 > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "test output" && git push origin main
