#!/bin/bash
cd /opt/pokemon-monitor-v2

DISPLAY=:99 ./venv/bin/python3 infra/test_prestaged_submit.py > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "test output" && git push origin main
