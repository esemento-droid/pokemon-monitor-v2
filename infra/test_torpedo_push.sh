#!/bin/bash
cd /opt/pokemon-monitor-v2

# Test: API ATC on OOS product (9419 = Pakiet 30th, should be OOS)
./venv/bin/python3 infra/test_oos_atc.py > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
git add torpedo_test_output.txt 2>/dev/null; git commit -m "test output" && git push origin main
