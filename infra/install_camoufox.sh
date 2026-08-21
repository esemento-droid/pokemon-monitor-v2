#!/bin/bash
# Install Camoufox on VPS
# Run: bash infra/install_camoufox.sh

set -e
cd /opt/pokemon-monitor-v2

echo "=== Installing Camoufox ==="
./venv/bin/pip install camoufox

echo "=== Fetching Camoufox browser binary ==="
./venv/bin/python3 -m camoufox fetch

echo "=== Verifying installation ==="
./venv/bin/python3 -c "from camoufox.async_api import AsyncCamoufox; print('Camoufox OK')"

echo "=== Done! Restart monitor to activate ==="
echo "sudo systemctl restart pokemon-monitor-v2"
