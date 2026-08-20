#!/bin/bash
cd /opt/pokemon-monitor-v2
DISPLAY=:99 ./venv/bin/python3 infra/sniff_jc_checkout.py > /tmp/torpedo_result.txt 2>&1
cp /tmp/torpedo_result.txt torpedo_test_output.txt
if [ -f /tmp/jc_sniff_result.json ]; then
  cp /tmp/jc_sniff_result.json torpedo_sniff.json
fi
git add torpedo_test_output.txt torpedo_sniff.json 2>/dev/null; git commit -m "sniff output" && git push origin main
