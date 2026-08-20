#!/bin/bash
cd /opt/pokemon-monitor-v2
DISPLAY=:99 ./venv/bin/python3 japancollectibles_torpedo.py fire --test --product-id 7437 > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt && git commit -m "test output" && git push origin main
